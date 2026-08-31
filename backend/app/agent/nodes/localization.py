import io
import json
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional

import requests
from langchain_core.messages import HumanMessage, SystemMessage
from PIL import Image, ImageDraw, ImageFont

from app.agent.state import AgentState
from app.agent.nodes.product import _local_image_to_data_uri
from app.config import get_settings
from app.services.llm import get_llm
from app.services.media import edit_image_async

logger = logging.getLogger(__name__)

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

# ── Pillow 叠层工具：将译文绘制到原图上，生成可直接使用的本地化素材 ──

# 位置关键词 → (垂直中心百分比, 水平对齐)
_POSITION_MAP = {
    "顶部": (0.08, "center"), "上方": (0.08, "center"), "横幅": (0.08, "center"),
    "底部": (0.92, "center"), "下方": (0.92, "center"),
    "居中": (0.50, "center"), "中间": (0.50, "center"), "中央": (0.50, "center"),
    "左上": (0.12, "left"), "右上": (0.12, "right"),
    "左下": (0.88, "left"), "右下": (0.88, "right"),
    "左侧": (0.50, "left"), "右侧": (0.50, "right"),
    "左下角": (0.88, "left"), "右上角": (0.12, "right"),
    "右下角": (0.88, "right"), "左上角": (0.12, "left"),
}


def _position_to_band(position_str: str, img_w: int, img_h: int):
    """将自然语言位置描述转换为像素坐标带 (y_center, band_height, h_align)"""
    y_ratio, h_align = 0.50, "center"
    if position_str:
        for keyword, (yr, ha) in _POSITION_MAP.items():
            if keyword in position_str:
                y_ratio, h_align = yr, ha
                break
    y_center = int(img_h * y_ratio)
    band_h = max(int(img_h * 0.14), 50)
    return y_center, band_h, h_align


def _load_flexible_font(size: int) -> ImageFont.FreeTypeFont:
    """按优先级尝试加载系统字体，失败时回退到 Pillow 默认字体"""
    candidates = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def _wrap_text_to_fit(text: str, font, max_width: int, draw: ImageDraw.Draw):
    """将文本换行以适配给定宽度，返回 (多行文本, 总高度)"""
    words = text.split()
    lines, current_line = [], ""
    for word in words:
        test = f"{current_line} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current_line = test
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    if not lines:
        lines = [text]
    line_h = draw.textbbox((0, 0), "Ag", font=font)[3] + 4
    return lines, len(lines) * line_h


async def _overlay_text_with_pillow(
    image_url: str, texts: List[Dict[str, Any]]
) -> Optional[str]:
    """用 Pillow 将译文叠层绘制到原图上，生成可直接使用的本地化图片。
    返回 /uploads/xxx.png 路径；失败返回 None。
    """
    if not texts:
        return None
    try:
        # ── 加载原图 ──
        if image_url.startswith("/uploads/"):
            settings = get_settings()
            fp = os.path.join(settings.upload_dir, os.path.basename(image_url))
            img = Image.open(fp)
        elif image_url.startswith(("http://", "https://")):
            resp = requests.get(image_url, timeout=20)
            resp.raise_for_status()
            img = Image.open(io.BytesIO(resp.content))
        else:
            return None

        img = img.convert("RGBA")
        overlay = img.copy()
        draw = ImageDraw.Draw(overlay)
        w, h = img.size

        for txt_item in texts:
            translated = txt_item.get("translated", "")
            position = txt_item.get("position", "")
            if not translated:
                continue

            y_center, band_h, h_align = _position_to_band(position, w, h)
            band_top = max(0, y_center - band_h // 2)
            band_bottom = min(h, y_center + band_h // 2)
            margin = int(w * 0.04)

            # 半透明白色遮罩覆盖原文区域
            draw.rectangle(
                [(0, band_top), (w, band_bottom)],
                fill=(255, 255, 255, 210),
            )

            # 根据可用空间计算字号
            avail_h = band_bottom - band_top
            font_size = max(14, min(int(avail_h * 0.45), int(w * 0.045), 52))
            font = _load_flexible_font(font_size)

            avail_w = w - margin * 2
            lines, total_text_h = _wrap_text_to_fit(translated, font, avail_w, draw)
            text_y = y_center - total_text_h // 2

            for line in lines:
                bbox = draw.textbbox((0, 0), line, font=font)
                line_w = bbox[2] - bbox[0]
                if h_align == "center":
                    text_x = (w - line_w) // 2
                elif h_align == "right":
                    text_x = w - line_w - margin
                else:
                    text_x = margin
                draw.text((text_x, text_y), line, fill=(40, 40, 40, 255), font=font)
                text_y += draw.textbbox((0, 0), line, font=font)[3] + 4

        # ── 保存到 uploads 目录 ──
        settings = get_settings()
        os.makedirs(settings.upload_dir, exist_ok=True)
        out_name = f"localized_{uuid.uuid4().hex[:10]}.png"
        final = overlay.convert("RGB")
        final.save(os.path.join(settings.upload_dir, out_name), "PNG")
        return f"/uploads/{out_name}"
    except Exception as e:
        logger.exception("Pillow overlay failed for %s: %s", image_url, e)
        return None


async def _localize_image_with_ai_edit(
    image_url: str, texts: List[Dict[str, Any]], target_lang: str
) -> Optional[str]:
    """用 AI 图片编辑模型（wan2.5-i2i-preview）重绘图片，将中文文字替换为英文。
    返回本地保存后的 /uploads/xxx.png 路径；失败返回 None。
    """
    if not texts:
        return None
    try:
        # 构建翻译对照表
        translation_pairs = []
        for t in texts:
            orig = t.get("original", "")
            trans = t.get("translated", "")
            if orig and trans:
                translation_pairs.append(f'"{orig}" → "{trans}"')

        if not translation_pairs:
            return None

        translations_text = "\n".join(translation_pairs)
        lang_label = MARKET_LANGUAGE_LABEL.get(target_lang, target_lang)

        prompt = (
            f"请将这张商品详情页图片中的所有中文文字替换为自然、准确、适合海外电商使用的英文。\n\n"
            f'**重要：这不是简单的"在图片上覆盖文本"，而是对原图片进行视觉级文字替换和重绘。**\n\n'
            f"请严格按照以下流程处理：\n\n"
            f"1. **识别图片中的中文**\n"
            f"   - 找出图片中所有可见中文，包括标题、副标题、卖点、参数、按钮、标签、说明文字、装饰性文字等。\n"
            f"   - 不要遗漏任何中文。\n"
            f"   - 品牌名称、产品型号、专有名词如果不应该翻译，请保持原样。\n\n"
            f"2. **中文 → 英文**\n"
            f"   - 将中文翻译成自然、简洁、符合欧美电商商品详情页习惯的英文。\n"
            f"   - 不要逐字直译，要根据商品营销语境进行本地化表达。\n"
            f"   - 英文长度尽量控制在与原中文相近的视觉范围内。\n"
            f"   - 如果原文是营销文案，请翻译成自然的英文营销表达，而不是生硬的机器翻译。\n\n"
            f"3. **删除原中文**\n"
            f"   - 完整移除原图片中的中文文字。\n"
            f"   - 恢复中文原来所在区域的背景、纹理、渐变、阴影、产品边缘和其他视觉元素。\n"
            f"   - 不要留下中文残影、模糊块、白色遮罩、明显修补痕迹或不自然的背景。\n\n"
            f"4. **重新绘制英文**\n"
            f"   - 将英文直接融入原图片设计。\n"
            f"   - 保持原文字的：字体风格、字重、字号比例、行距、字间距、对齐方式、颜色、阴影、描边、透明度、透视关系、弧形/旋转效果。\n"
            f"   - 如果原文字位于产品包装、衣服、广告牌、屏幕或其他具有透视关系的表面，请让英文遵循原表面的透视和形变。\n"
            f"   - 如果原文是艺术字体、粗体、细体、手写体或特殊排版，请尽可能复现原来的视觉风格。\n\n"
            f"5. **保持原图不变**\n"
            f"   - 商品本身不能发生任何改变。\n"
            f"   - 不改变产品颜色、材质、结构、尺寸、Logo、图案和细节。\n"
            f"   - 不改变人物、模特、姿态、五官、服装和背景。\n"
            f"   - 不改变原图片的构图、比例、摄影效果和光影。\n"
            f"   - 只替换中文文字及其必要的背景修复区域。\n\n"
            f"6. **版式适配**\n"
            f"   - 英文如果比中文更长，不要让文字溢出原来的设计区域。\n"
            f"   - 可以适当调整英文的字号、字间距、换行方式，使整体版式与原图保持一致。\n"
            f"   - 不要为了容纳英文而改变商品图片的整体布局。\n\n"
            f"**最终目标：**\n"
            f"让处理后的图片看起来像设计师从一开始就制作了一张英文版商品详情页，而不是在中文图片上后期覆盖了一层英文文字。\n\n"
            f"请输出一张完整的英文版商品详情图，保持原图片的高清质量和原始画幅比例。不要出现AI生成的字眼。\n\n"
            f"**参考翻译对照表（请优先使用以下译文，未列出的中文请自行翻译）：**\n"
            f"{translations_text}"
        )

        logger.info("AI 图片编辑本地化：调用 edit_image_async, 翻译 %d 组文案", len(texts))

        # 调用图片编辑模型（异步任务，内部自动轮询）
        import asyncio
        result_url = await asyncio.to_thread(
            edit_image_async, prompt, image_url, "1024*1024"
        )

        if not result_url:
            logger.warning("AI 图片编辑返回空结果")
            return None

        # 下载结果图并保存到本地（OSS 签名 URL 24h 过期，需持久化）
        resp = requests.get(result_url, timeout=30)
        resp.raise_for_status()
        settings = get_settings()
        os.makedirs(settings.upload_dir, exist_ok=True)
        out_name = f"localized_ai_{uuid.uuid4().hex[:10]}.png"
        out_path = os.path.join(settings.upload_dir, out_name)
        with open(out_path, "wb") as f:
            f.write(resp.content)

        logger.info("AI 本地化完成，结果已保存: %s", f"/uploads/{out_name}")
        return f"/uploads/{out_name}"

    except Exception as e:
        logger.exception("AI 图片编辑本地化失败: %s", e)
        return None


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

        if item["has_text"] and item["texts"]:
            # 优先方案：AI 图片编辑模型重绘（中文→英文，效果最自然）
            ai_url = await _localize_image_with_ai_edit(url, item["texts"], target_lang)
            if ai_url:
                item["localized_image"] = ai_url
                item["engine"] = "ai_image_edit"
            else:
                # 降级方案：Pillow 叠层（白色遮罩 + 英文文字覆盖）
                pillow_url = await _overlay_text_with_pillow(url, item["texts"])
                if pillow_url:
                    item["localized_image"] = pillow_url
                    item["engine"] = "qwen_vl_pillow_overlay"

        localized_items.append(item)

    translated_count = sum(1 for i in localized_items if i.get("localized_image"))
    text_pair_count = sum(len(i.get("texts", [])) for i in localized_items)
    ai_edit_count = sum(1 for i in localized_items if i.get("engine") == "ai_image_edit")
    pillow_count = sum(1 for i in localized_items if i.get("engine") == "qwen_vl_pillow_overlay")
    lang_label = MARKET_LANGUAGE_LABEL.get(target_lang, target_lang)

    # 实际引擎标签：优先反映 AI 重绘是否成功
    effective_engine = engine
    if ai_edit_count > 0:
        effective_engine = "ai_image_edit"
    elif pillow_count > 0:
        effective_engine = "qwen_vl_pillow_overlay"

    result = {
        "target_language": target_lang,
        "engine": effective_engine,
        "items": localized_items,
    }

    trace_item = {
        "node": "image_localization",
        "status": "completed",
        "summary": f"图片本地化完成：处理 {len(localized_items)} 张详情图 → {lang_label}（AI 重绘 {ai_edit_count} 张，Pillow 叠层 {pillow_count} 张，文案译文 {text_pair_count} 组）",
        "timestamp": time.time(),
        "detail": {"count": len(localized_items), "engine": effective_engine, "ai_image_edit": ai_edit_count, "pillow_overlay": pillow_count}
    }

    current_trace = state.get("trace", []) or []

    return {
        "localized_images": result,
        "current_node": "image_localization",
        "trace": current_trace + [trace_item]
    }
