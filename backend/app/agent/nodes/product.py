import base64
import json
import logging
import mimetypes
import os
import time
from typing import Dict, Any, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.state import AgentState
from app.config import get_settings
from app.services.llm import get_llm

logger = logging.getLogger(__name__)

PROMPT_PRODUCT_VISION = """你是一个专业的跨境电商商品分析师和多模态属性识别专家，精通全品类商品（服装、3C 电子、家居、美妆、玩具、户外运动等）的结构化拆解。
请仔细观察用户上传的商品图片，先判断商品所属品类大类，再提取该品类的关键结构化属性，以便用于后续的选品分析和海外 Listing 文案撰写。

请严格输出合法的 JSON 对象，不要包含任何 markdown 代码块标记，不要包含多余文字。
JSON 字段规范：
{
  "category_family": "品类大类，只能从以下枚举取值：apparel(服装鞋帽) / electronics(3C电子) / home(家居百货) / beauty(美妆个护) / toys(玩具母婴) / outdoor(户外运动) / general(其他)",
  "category": "细分品类名称（如：法式复古碎花长裙 / 无线蓝牙耳机 / 不锈钢保温杯）",
  "main_color": "主色调与外观描述",
  "materials": ["核心材质/面料/用料列表，如：棉麻, 透气雪纺 或 ABS塑料, 304不锈钢"],
  "key_specs": ["可识别的关键规格参数（如尺寸、容量、功率、接口、重量等，服装类填尺码特征），无法判断则留空数组"],
  "style_tags": ["设计风格/核心卖点标签，如：法式复古, 便携折叠, 静音低功耗"],
  "design_features": ["核心结构、版型或功能细节特点"],
  "target_gender": "适用人群性别（女 / 男 / 中性 / 儿童 / 不适用）",
  "season": "适用季节（如：春夏 / 四季通用）",
  "target_occasions": ["适用场景，如：度假旅行, 日常通勤, 户外露营, 居家办公"]
}
"""

def _local_image_to_data_uri(image_url: str) -> Optional[str]:
    """将本地图片文件（/uploads/ 或本地绝对路径）转为 base64 data URI，供云端大模型与生图 API 读取"""
    if not image_url:
        return None
    if image_url.startswith("data:"):
        return image_url
    if image_url.startswith(("http://", "https://")):
        return None  # 已经是公网 URL

    file_path = None
    if os.path.isfile(image_url):
        file_path = image_url
    elif image_url.startswith("/uploads/"):
        settings = get_settings()
        filename = os.path.basename(image_url)
        cand = os.path.join(settings.upload_dir, filename)
        if os.path.isfile(cand):
            file_path = cand

    if not file_path or not os.path.isfile(file_path):
        return None

    mime = mimetypes.guess_type(file_path)[0] or "image/jpeg"
    with open(file_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{encoded}"

async def product_node(state: AgentState) -> Dict[str, Any]:
    """商品属性提取节点：1688 真实数据优先，VL 视觉补充"""
    image_url = state.get("product_image_url")
    category = state.get("product_category", "")

    # ── 检查是否有 1688 真实数据 ──
    title_1688 = state.get("product_title", "")
    price_1688 = state.get("supply_price_cny")
    sku_attrs = state.get("sku_attributes", {})
    source_url = state.get("source_url", "")

    if title_1688:
        # ── 路径 A：1688 导入，真实数据为主 ──
        attributes = {
            "title": title_1688,
            "supply_price_cny": price_1688,
            "source_url": source_url,
            "sku_attributes": sku_attrs,
            "main_image_url": image_url or "",
            "original_images": state.get("imported_images", []),
        }
        # 如果有图片，仍用 VL 补充视觉属性（颜色、材质、风格等）
        vision_url = _local_image_to_data_uri(image_url) or image_url if image_url else None
        if vision_url:
            vision_attrs = await _extract_vision_attributes(vision_url, title_1688, category)
            # VL 结果补充，不覆盖真实数据
            for k, v in vision_attrs.items():
                if k not in ("title", "supply_price_cny", "source_url", "sku_attributes"):
                    attributes[k] = v
        else:
            # 无图片的纯数据模式，用 LLM 从标题推断品类
            text_attrs = await _infer_from_title(title_1688)
            attributes.update(text_attrs)
    else:
        # ── 路径 B：拍照/上传，VL 全量提取（现有逻辑）──
        if not image_url:
            image_url = "https://img.alicdn.com/imgextra/i1/6000000007892/O1CN01a2ZpQM1scXS5sBsAa_!!6000000007892-0-tps-400-400.jpg"

        vision_url = _local_image_to_data_uri(image_url) or image_url
        attributes = await _extract_vision_attributes(vision_url, "", category)
        # 确保关键字段存在
        attributes.setdefault("main_image_url", image_url or "")
        attributes.setdefault("original_images", state.get("imported_images", []))

    # ── 兜底：关键展示字段绝不为 None ──
    attributes.setdefault("title", title_1688 or "未命名商品")
    attributes.setdefault("supply_price_cny", price_1688)
    _cf = attributes.get("category_family")
    _valid_families = ("apparel", "electronics", "home", "beauty", "toys", "outdoor", "general")
    if not _cf or str(_cf).strip().lower() not in _valid_families:
        attributes["category_family"] = "general"

    # category 多级兜底：VL输出 → 用户传入 → 标题截取 → 固定默认
    # 用 _is_blank 统一处理 None / 空字符串 / 纯空白 / "N/A" 等无效值
    _cat = attributes.get("category")
    if not _cat or (isinstance(_cat, str) and not _cat.strip()) or str(_cat).strip().lower() in ("n/a", "none", "null", "unknown", "未知"):
        if category and category.strip():
            attributes["category"] = category.strip()
        elif title_1688 and title_1688.strip():
            attributes["category"] = title_1688[:30]
        else:
            attributes["category"] = "跨境商品"

    # materials / style_tags / design_features 兜底为空列表（避免 join 报错）
    for list_field in ("materials", "style_tags", "design_features", "key_specs", "target_occasions"):
        if not isinstance(attributes.get(list_field), list):
            attributes[list_field] = []

    # ── 核心属性完整性强制校验：材质/颜色/规格(尺码) 必须填充 ──
    # 合规质检要求这些字段不能为空，否则 Listing 无法通过上架审核
    _missing_core = []
    if not attributes.get("materials") or (isinstance(attributes["materials"], list) and not any(m.strip() for m in attributes["materials"] if isinstance(m, str))):
        _missing_core.append("materials")
    if not attributes.get("main_color") or (isinstance(attributes["main_color"], str) and not attributes["main_color"].strip()):
        _missing_core.append("main_color")
    if not attributes.get("key_specs") or (isinstance(attributes["key_specs"], list) and not any(s.strip() for s in attributes["key_specs"] if isinstance(s, str))):
        _missing_core.append("key_specs")

    if _missing_core:
        # 尝试用 LLM 从标题/已有属性推断缺失字段
        inferred = await _infer_missing_attributes(
            title=title_1688,
            category=attributes.get("category", ""),
            category_family=attributes.get("category_family", "general"),
            existing_attributes=attributes,
            missing_fields=_missing_core,
        )
        for field, value in inferred.items():
            if value:
                attributes[field] = value
                logger.info("属性补全：%s = %s", field, value)

    attr_count = sum(1 for v in attributes.values() if v)

    trace_item = {
        "node": "extract_attributes",
        "status": "completed",
        "summary": f"已识别商品【{attributes.get('category')}】（{attributes.get('category_family', 'general')}），提取 {attr_count} 项核心结构化属性",
        "timestamp": time.time(),
        "detail": attributes
    }

    current_trace = state.get("trace", []) or []

    return {
        "product_attributes": attributes,
        "product_category": attributes.get("category", category),
        "current_node": "extract_attributes",
        "trace": current_trace + [trace_item]
    }


async def _extract_vision_attributes(vision_url: str, title_hint: str, category: str) -> Dict[str, Any]:
    """调用 VL 多模态模型从图片提取视觉属性"""
    llm = get_llm(temperature=0.2)
    try:
        title_hint_text = f"（参考商品标题：{title_hint}）" if title_hint else ""
        category_hint = f"（参考提示：该商品可能属于【{category}】）" if category else ""
        messages = [
            SystemMessage(content=PROMPT_PRODUCT_VISION),
            HumanMessage(content=[
                {"type": "text", "text": f"请分析这款商品的图片并提取其结构化特征属性{title_hint_text}{category_hint}："},
                {"type": "image_url", "image_url": {"url": vision_url}}
            ])
        ]
        response = await llm.ainvoke(messages)
        content = response.content.strip()

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        return json.loads(content)
    except Exception:
        # VL 失败 返回空，由调用方决定降级
        return {}


async def _infer_from_title(title: str) -> Dict[str, Any]:
    """无图片时，用 LLM 从标题推断品类和视觉特征"""
    llm = get_llm(temperature=0.3)
    try:
        messages = [
            SystemMessage(content=f"根据商品标题推断品类和视觉特征。输出 JSON，字段同 VL 提取规范。"),
            HumanMessage(content=f"商品标题：{title}")
        ]
        response = await llm.ainvoke(messages)
        content = response.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        return json.loads(content)
    except Exception:
        return {
            "category_family": "general",
            "category": title[:20] if title else "未命名商品",
            "main_color": "未知",
            "materials": [],
            "key_specs": [],
            "style_tags": [],
            "design_features": [],
            "target_gender": "中性",
            "season": "四季通用",
            "target_occasions": []
        }


async def _infer_missing_attributes(
    title: str,
    category: str,
    category_family: str,
    existing_attributes: Dict[str, Any],
    missing_fields: List[str],
) -> Dict[str, Any]:
    """用 LLM 从标题和品类推断缺失的核心属性（材质/颜色/规格），确保合规质检通过。"""
    llm = get_llm(temperature=0.2)
    fields_desc = {
        "materials": "材质/面料（如：Cotton, Polyester, ABS Plastic, Stainless Steel 等）",
        "main_color": "主色调（如：Black, Navy Blue, White 等）",
        "key_specs": "规格参数（服装类填尺码范围如 S-XXL，其他品类填尺寸/容量/功率等）",
    }
    try:
        missing_desc = "\n".join(f"- {f}: {fields_desc.get(f, '未知字段')}" for f in missing_fields)
        existing_summary = {k: v for k, v in existing_attributes.items()
                           if k in ("category", "category_family", "title", "style_tags", "design_features")}
        prompt = (
            f"你是一名跨境电商商品属性专家。以下商品缺少核心属性信息，请根据标题、品类和已有信息推断缺失字段。\n\n"
            f"商品已有信息：{json.dumps(existing_summary, ensure_ascii=False)}\n"
            f"缺失字段：\n{missing_desc}\n\n"
            f"推断规则：\n"
            f"1. 根据品类给出最合理的默认值（服装类材质通常为 Cotton/Polyester，颜色从标题提取）\n"
            f"2. 服装类 key_specs 必须包含尺码范围（如 S/M/L/XL/XXL）\n"
            f"3. 材质用英文输出，颜色用英文输出，规格用英文输出\n"
            f"4. 只输出缺失字段，不要输出其他内容\n\n"
            f"请输出 JSON 对象，仅包含缺失的字段名和推断值。"
        )
        messages = [
            SystemMessage(content="输出纯 JSON，不含 markdown 代码块。"),
            HumanMessage(content=prompt),
        ]
        response = await llm.ainvoke(messages)
        content = response.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        result = json.loads(content)
        # 确保返回的字段确实在 missing_fields 中
        return {k: v for k, v in result.items() if k in missing_fields and v}
    except Exception as e:
        logger.warning("LLM 推断缺失属性失败: %s，使用硬编码兜底", e)
        # 硬编码兜底：根据品类给出最保守的默认值
        fallback = {}
        if "materials" in missing_fields:
            if category_family == "apparel":
                fallback["materials"] = ["Cotton", "Polyester"]
            elif category_family == "electronics":
                fallback["materials"] = ["ABS Plastic", "Metal"]
            else:
                fallback["materials"] = ["Standard Material"]
        if "main_color" in missing_fields:
            fallback["main_color"] = "Black"
        if "key_specs" in missing_fields:
            if category_family == "apparel":
                fallback["key_specs"] = ["S", "M", "L", "XL", "XXL"]
            else:
                fallback["key_specs"] = ["Standard Size"]
        return fallback
