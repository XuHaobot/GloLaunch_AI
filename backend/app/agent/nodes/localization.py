import json
import time
from typing import Any, Dict, List, Optional
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.state import AgentState
from app.agent.nodes.product import _local_image_to_data_uri
from app.config import get_settings
from app.services.llm import get_llm

# 目标市场 -> 图片文字本地化语言
MARKET_LANGUAGE = {
    "US": "en",
    "EU": "en",  # 欧区默认英语，后续可扩展多语言批次
    "Southeast Asia": "en",
}

MARKET_LANGUAGE_LABEL = {"en": "英语 (English)"}

PROMPT_IMAGE_LOCALIZE = """你是一名跨境电商详情页视觉本地化专家。请识别图片中的所有中文文案（促销语、卖点标注、参数文字等），
并将其翻译为地道的目标语言电商文案，同时给出排版建议。不要逐字直译，要符合海外详情页的表达习惯。

请严格输出合法的 JSON 对象，不要包含任何 markdown 代码块标记，不要包含多余文字。
JSON 字段规范：
{
  "has_text": true,
  "texts": [
    {"original": "图片中的中文原文", "translated": "目标语言译文", "position": "文字大致位置（如 顶部横幅/左下角/居中）", "style_hint": "字体与颜色保持建议"}
  ]
}
若图片中没有中文文字，输出 {"has_text": false, "texts": []}
"""

def _get_alimt_client():
    """构建阿里云电商图翻客户端（未安装 SDK 或未配置 AK 时返回 None）"""
    settings = get_settings()
    if not settings.alimt_access_key_id or not settings.alimt_access_key_secret:
        return None
    try:
        from alibabacloud_alimt20190102.client import Client as AlimtClient
        from alibabacloud_tea_openapi import models as open_api_models
    except ImportError:
        return None
    config = open_api_models.Config(
        access_key_id=settings.alimt_access_key_id,
        access_key_secret=settings.alimt_access_key_secret,
    )
    config.endpoint = settings.alimt_endpoint
    return AlimtClient(config)

def _translate_image_with_alimt(client, image_url: str, source_lang: str, target_lang: str) -> Optional[str]:
    """调用阿里云电商图片翻译，返回译后图 URL（响应结构多版本兼容解析）"""
    from alibabacloud_alimt20190102 import models as alimt_models
    from alibabacloud_tea_util import models as util_models

    request = alimt_models.TranslateImageRequest(
        image_url=image_url, source_language=source_lang, target_language=target_lang
    )
    runtime = util_models.RuntimeOptions()
    resp = client.translate_image_with_options(request, runtime)
    body = getattr(resp, "body", None)
    data = getattr(body, "data", None)
    final_url = getattr(data, "final_image_url", None) or getattr(data, "image_url", None)
    if final_url:
        return final_url
    # 兜底：序列化响应体查找 URL 字段
    try:
        payload = body.to_map()
    except Exception:
        return None
    stack = [payload]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                if isinstance(v, str) and v.startswith("http") and ("image" in k.lower() or "url" in k.lower()):
                    return v
                stack.append(v)
        elif isinstance(cur, list):
            stack.extend(cur)
    return None

async def _localize_with_vision(image_url: str, target_lang: str) -> Dict[str, Any]:
    """Qwen-VL 兜底方案：识别图中中文并翻译，产出译文+排版建议（前端叠层展示）"""
    llm = get_llm(temperature=0.2)
    # 本地上传图转 base64 data URI（外部模型无法访问本机链接）
    vision_url = _local_image_to_data_uri(image_url) or image_url
    try:
        messages = [
            SystemMessage(content=PROMPT_IMAGE_LOCALIZE),
            HumanMessage(content=[
                {"type": "text", "text": f"请将这张电商详情页图片中的中文文案本地化为 {MARKET_LANGUAGE_LABEL.get(target_lang, target_lang)}："},
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
        return {"has_text": False, "texts": [], "fallback_note": "该图未识别到可本地化文案或识别服务暂不可用"}

async def localization_node(state: AgentState) -> Dict[str, Any]:
    """详情页图片文字本地化节点：中文图 → 目标语言图（阿里云电商图翻优先，Qwen-VL 兜底）"""
    market = state.get("target_market", "US")
    target_lang = MARKET_LANGUAGE.get(market, "en")

    # 待本地化图片：1688 搬运的详情图优先，其次主图（最多处理 3 张控制成本）
    candidates: List[str] = list(state.get("imported_images") or [])
    main_img = state.get("product_image_url")
    if main_img and main_img not in candidates:
        candidates.append(main_img)
    candidates = [u for u in candidates if u][:3]

    client = _get_alimt_client()
    engine = "aliyun_image_translation" if client else "qwen_vl_localization"

    localized_items = []
    for url in candidates:
        item: Dict[str, Any] = {"source_image": url, "target_lang": target_lang, "engine": engine}
        if client:
            try:
                final_url = _translate_image_with_alimt(client, url, "zh", target_lang)
                if final_url:
                    item["localized_image"] = final_url
                    localized_items.append(item)
                    continue
            except Exception as e:
                item["engine_error"] = str(e)[:200]
                item["engine"] = "qwen_vl_localization"

        # 兜底：Qwen-VL 识别 + 翻译（产出译文与排版建议）
        vision_result = await _localize_with_vision(url, target_lang)
        item["texts"] = vision_result.get("texts", [])
        item["has_text"] = vision_result.get("has_text", False)
        localized_items.append(item)

    translated_count = sum(1 for i in localized_items if i.get("localized_image"))
    text_pair_count = sum(len(i.get("texts", [])) for i in localized_items)
    lang_label = MARKET_LANGUAGE_LABEL.get(target_lang, target_lang)

    result = {
        "target_language": target_lang,
        "engine": engine,
        "items": localized_items,
    }

    trace_item = {
        "node": "image_localization",
        "status": "completed",
        "summary": f"图片本地化完成：处理 {len(localized_items)} 张详情图 → {lang_label}（整图重绘 {translated_count} 张，文案译文 {text_pair_count} 组）",
        "timestamp": time.time(),
        "detail": {"count": len(localized_items), "engine": engine}
    }

    current_trace = state.get("trace", []) or []

    return {
        "localized_images": result,
        "current_node": "image_localization",
        "trace": current_trace + [trace_item]
    }
