import asyncio
import time
from typing import Dict, Any, List

from app.agent.state import AgentState
from app.config import get_settings
from app.services.media import generate_image, edit_image_async

# 品类大类 → 海外生活方式场景模板（真实生图的 prompt 基底，兜底素材同步复用）
SCENE_TEMPLATES: Dict[str, List[Dict[str, str]]] = {
    "apparel": [
        {"scene_name": "阳光度假庄园", "style": "French Cottagecore Lifestyle",
         "scene": "a sunlit European countryside garden with warm morning light"},
        {"scene_name": "海滨木栈道漫步", "style": "Beach Vacation",
         "scene": "a seaside wooden boardwalk with gentle ocean breeze at golden hour"},
        {"scene_name": "城市露天咖啡馆", "style": "Urban Cafe Street",
         "scene": "a cozy outdoor cafe street in a European city, soft afternoon light"},
    ],
    "electronics": [
        {"scene_name": "极简桌面办公", "style": "Minimal Desk Setup",
         "scene": "a clean minimalist desk setup with soft studio lighting"},
        {"scene_name": "户外出行场景", "style": "Outdoor Travel",
         "scene": "an outdoor travel scene with the product in a backpack context"},
        {"scene_name": "居家影音角落", "style": "Home Entertainment Corner",
         "scene": "a modern home entertainment corner with ambient warm light"},
    ],
    "default": [
        {"scene_name": "明亮居家场景", "style": "Bright Home Lifestyle",
         "scene": "a bright modern living room with natural window light"},
        {"scene_name": "户外使用场景", "style": "Outdoor Usage",
         "scene": "an outdoor lifestyle scene showing the product in real usage"},
        {"scene_name": "细节特写氛围", "style": "Detail Close-up Mood",
         "scene": "a macro close-up shot highlighting product texture and details"},
    ],
}

# FALLBACK_SCENES 已移除：不再使用 Unsplash 预设素材填充，生图失败时如实记录缺口

# ── 虚拟试穿：直接调用本地 aitryon 模块（DashScope aitryon 模型） ──
from app.services.aitryon import generate_tryon as _aitryon_generate


async def _tryon_with_aitryon(product_image_url: str, product_desc: str = "") -> Dict[str, Any]:
    """调用本地 aitryon 模块（DashScope aitryon 专用试穿模型）。
    流程：下载商品图 → 生成模特底图 → 上传 OSS → aitryon 合成 → 保存到本地。
    失败抛出异常由调用方降级。
    """
    result = await _aitryon_generate(product_image_url, product_desc)
    if not result.get("success") or not result.get("image_url"):
        raise ValueError(result.get("message", "aitryon 试穿失败"))
    return {
        "model_type": "AI Virtual Try-On (DashScope aitryon)",
        "tryon_image_url": result["image_url"],
        "garment_fit_status": result.get("message", "Virtual try-on completed"),
        "fabric_drape_retention": "DashScope aitryon model synthesis",
        "engine": "aitryon",
    }

def _fallback_tryon() -> Dict[str, Any]:
    """预设虚拟试穿兜底（不再使用 Unsplash，返回空状态）"""
    return {
        "model_type": "N/A",
        "tryon_image_url": "",
        "garment_fit_status": "Unavailable - all try-on engines failed",
        "fabric_drape_retention": "N/A",
        "engine": "none",
    }

def _tryon_with_image_edit(product_image_url: str, product_desc: str) -> Dict[str, Any]:
    """用图编辑模型（wan2.5-i2i）合成真实模特上身图，失败抛异常由调用方降级"""
    prompt = (
        f"Put this exact garment on a young European female fashion model, full body standing pose, "
        f"natural studio lighting, white seamless background, e-commerce lookbook photo, "
        f"preserve the garment's exact color, pattern and fabric texture. Product: {product_desc}"
    )
    # 本地上传图外部模型不可达，无法参与图编辑合成
    if not product_image_url or product_image_url.startswith("/uploads/") or product_image_url.startswith("data:"):
        raise ValueError("本地图无法用于远端图编辑合成")
    result_url = edit_image_async(prompt, product_image_url)
    if not result_url:
        raise ValueError("图编辑试穿任务未返回结果")
    return {
        "model_type": "AI Generated European Female Model",
        "tryon_image_url": result_url,
        "garment_fit_status": "AI Synthesized Fit (fabric & pattern preserved)",
        "fabric_drape_retention": "Source garment texture retained via image editing",
        "engine": "wan2.5-i2i-tryon",
    }

async def run_virtual_tryon(product_image_url: str, product_desc: str) -> Dict[str, Any]:
    """按需触发的虚拟试穿增值服务（不在主流水线内执行）。
    三级降级链：aitryon 专用服务 → 图编辑模型合成 → 预设演示兜底。
    """
    settings = get_settings()
    main_img = product_image_url or ""
    if settings.model_router_api_key:
        try:
            return await _tryon_with_aitryon(main_img)
        except Exception:
            pass
    try:
        return await asyncio.to_thread(_tryon_with_image_edit, main_img, product_desc)
    except Exception:
        pass
    return _fallback_tryon()

async def _generate_ai_scenes(product_desc: str, family: str, fallback_main: str = "",
                              identity: Dict[str, Any] = None) -> Dict[str, Any]:
    """AI 全量生图：白底主图 + 3 组生活方式场景图。
    生图失败时不再使用 Unsplash 填充，如实记录缺口。
    支持 Product Identity 约束以保持商品视觉一致性。
    """
    templates = SCENE_TEMPLATES.get(family, SCENE_TEMPLATES["default"])

    # ── Product Identity 约束 ──
    identity_constraint = ""
    if identity:
        visual = identity.get("visual_constraints", "")
        if visual:
            identity_constraint = f"\nIMPORTANT: {visual}. The product in the image must match these exact characteristics."

    # 并发调用生图引擎（白底主图 + 3 组场景图）
    prompts = [
        f"professional e-commerce product photography, pure white background, {product_desc}{identity_constraint}, high detail, studio lighting"
    ]
    prompts += [
        f"lifestyle photography of {product_desc}{identity_constraint}, {t['scene']}, photorealistic, e-commerce hero image"
        for t in templates
    ]
    results = await asyncio.gather(*(asyncio.to_thread(generate_image, p) for p in prompts))

    image_engine = "wan2.7-image-pro"
    white_main = results[0]
    if not white_main:
        white_main = fallback_main or ""
        image_engine = "none" if not any(results) else image_engine

    lifestyle_scenes = []
    for i, t in enumerate(templates):
        url = results[i + 1]
        if not url:
            continue  # 跳过失败的图片，不用 Unsplash 填充
        lifestyle_scenes.append({
            "scene_name": t["scene_name"],
            "image_url": url,
            "style": t["style"],
        })

    real_scene_count = sum(1 for r in results[1:] if r)
    failed_count = len([r for r in results if not r])
    if not results[0] and real_scene_count == 0:
        image_engine = "none"
    elif real_scene_count < len(templates) or not results[0]:
        image_engine = f"wan2.7-image-pro (AI 生成 {real_scene_count}/{len(templates)}, 失败 {failed_count})"

    return {
        "white_background_main": white_main,
        "lifestyle_scenes": lifestyle_scenes,
        "image_engine": image_engine,
        "material_mode": "generated",
        "generation_failures": failed_count,
    }

async def run_scene_generation(category: str = "跨境商品", category_family: str = "general",
                               style_tags: List[str] = None, design_features: List[str] = None,
                               product_image_url: str = "") -> Dict[str, Any]:
    """按需触发的 AI 场景图生成增值服务（不在主流水线内）：搬运商品补充海外生活方式场景图"""
    product_desc = ", ".join(
        [category] + (style_tags or [])[:3] + (design_features or [])[:3]
    )
    return await _generate_ai_scenes(product_desc, category_family, product_image_url)

def _build_product_identity(attrs: Dict[str, Any], product_image_url: str = "") -> Dict[str, Any]:
    """从 product_attributes 中提取视觉约束，确保 AI 生图保持商品视觉一致性。
    返回 identity dict，包含 visual_constraints 文本和关键视觉属性。
    """
    materials = attrs.get("materials", [])
    colors = attrs.get("colors", [])
    style_tags = attrs.get("style_tags", [])
    design_features = attrs.get("design_features", [])
    key_specs = attrs.get("key_specs", [])

    # 构建视觉约束描述
    constraints_parts = []
    if colors:
        constraints_parts.append(f"color: {', '.join(colors)}")
    if materials:
        constraints_parts.append(f"material: {', '.join(materials)}")
    if style_tags:
        constraints_parts.append(f"style: {', '.join(style_tags[:3])}")
    if design_features:
        constraints_parts.append(f"design details: {', '.join(design_features[:3])}")
    if key_specs:
        constraints_parts.append(f"specs: {', '.join(key_specs[:3])}")

    visual_constraints = "; ".join(constraints_parts) if constraints_parts else ""

    return {
        "visual_constraints": visual_constraints,
        "colors": colors,
        "materials": materials,
        "style_tags": style_tags,
        "has_source_image": bool(product_image_url),
    }


async def studio_node(state: AgentState) -> Dict[str, Any]:
    """AI 商品摄影节点（搬运优先、AI 按需补给）：
    - 用户已提供商品图（1688 搬运场景）→ 直接沿用原素材，不消耗生图额度；
    - 未提供素材 → Wan2.7 全量生图（白底主图 + 场景图，逐图失败如实记录）。
    通过 Product Identity Lock 确保 AI 生图与真实商品视觉一致。
    注：虚拟试穿与按需补图均为增值服务（run_virtual_tryon / run_scene_generation）。
    """
    attrs = state.get("product_attributes", {})
    category = attrs.get("category", state.get("product_category", "跨境商品"))
    family = attrs.get("category_family", "general")
    product_desc = ", ".join(
        [category] + attrs.get("style_tags", [])[:3] + attrs.get("design_features", [])[:3]
    )
    source_img = state.get("product_image_url") or ""

    # ── Product Identity Lock：提取视觉约束 ──
    identity = _build_product_identity(attrs, source_img)

    if source_img:
        # 搬运原素材模式：主图沿用原图，跳过 4 次生图调用；场景图可通过增值服务按需补充
        generated_assets = {
            "white_background_main": source_img,
            "lifestyle_scenes": [],
            "image_engine": "source_material",
            "material_mode": "source",
            "generation_failures": 0,
            "product_identity": identity,
        }
        summary = f"【{category}】搬运原素材沿用（主图直接复用），未触发 AI 生图，可按需补充场景图"
    else:
        generated_assets = await _generate_ai_scenes(product_desc, family, identity=identity)
        generated_assets["product_identity"] = identity
        failed = generated_assets.get("generation_failures", 0)
        summary = (f"AI 影棚生成完成【{category}】：白底主图 + {len(generated_assets['lifestyle_scenes'])} 组场景图"
                   f"（引擎 {generated_assets['image_engine']}）")
        if failed:
            summary += f"，{failed} 张生图失败已如实记录"

    trace_item = {
        "node": "studio_generation",
        "status": "completed",
        "summary": summary,
        "timestamp": time.time(),
        "detail": {
            "scene_count": len(generated_assets["lifestyle_scenes"]),
            "engine": generated_assets["image_engine"],
            "material_mode": generated_assets["material_mode"],
            "identity_locked": bool(identity.get("visual_constraints")),
            "generation_failures": generated_assets.get("generation_failures", 0),
        }
    }

    current_trace = state.get("trace", []) or []

    return {
        "studio_assets": generated_assets,
        "current_node": "studio_generation",
        "trace": current_trace + [trace_item]
    }
