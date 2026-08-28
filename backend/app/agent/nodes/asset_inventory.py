"""asset_inventory_node —— 素材盘点与缺口分析节点。

核心理念：「搬运优先，AI 按需补给」
先盘点已有素材（搬运 + 用户上传），识别缺口，
仅对缺口触发 AI 生成，节省额度和时间。
"""
import time
from typing import Dict, Any, List

from app.agent.state import AgentState
from app.domain.enums import AssetType, AssetSource
from app.domain.asset import (
    AssetInventory, AssetItem, AssetGap, AssetGapItem,
)


# 各平台对素材类型的要求定义
PLATFORM_ASSET_REQUIREMENTS = {
    "Amazon": {
        "required": [AssetType.MAIN_IMAGE],
        "recommended": [
            AssetType.LIFESTYLE_IMAGE, AssetType.INFOGRAPHIC,
            AssetType.SIZE_CHART, AssetType.VIDEO,
        ],
        "optional": [AssetType.A_PLUS_CONTENT, AssetType.PACKAGING],
    },
    "Shopee": {
        "required": [AssetType.MAIN_IMAGE],
        "recommended": [
            AssetType.LIFESTYLE_IMAGE, AssetType.INFOGRAPHIC,
            AssetType.SIZE_CHART,
        ],
        "optional": [AssetType.VIDEO],
    },
    "TikTok": {
        "required": [AssetType.MAIN_IMAGE, AssetType.VIDEO],
        "recommended": [AssetType.LIFESTYLE_IMAGE],
        "optional": [AssetType.INFOGRAPHIC],
    },
}

# 各素材类型的 AI 生成成本估算
ASSET_COST_MAP = {
    AssetType.MAIN_IMAGE: {"credits": 5, "seconds": 10},
    AssetType.LIFESTYLE_IMAGE: {"credits": 8, "seconds": 15},
    AssetType.INFOGRAPHIC: {"credits": 10, "seconds": 20},
    AssetType.SIZE_CHART: {"credits": 3, "seconds": 5},
    AssetType.VIDEO: {"credits": 20, "seconds": 30},
    AssetType.A_PLUS_CONTENT: {"credits": 15, "seconds": 25},
    AssetType.PACKAGING: {"credits": 5, "seconds": 10},
}


_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".svg"}


def _estimate_quality(url: str, source: str, context: dict) -> float:
    """Estimate asset quality based on URL heuristics and source type.

    Args:
        url: The image/media URL (may be empty or None).
        source: One of "user_provided", "imported", "ai_generated".
        context: Extra context — e.g. {"imported_total": N} for imported bonus.

    Returns:
        A float in [0.0, 0.95].
    """
    if not url:
        return 0.0

    score = 0.0

    if source == AssetSource.USER_PROVIDED:
        score = 0.75
        lower = url.lower().split("?")[0]  # strip query params
        if any(lower.endswith(ext) for ext in _IMAGE_EXTENSIONS):
            score += 0.10

    elif source == AssetSource.IMPORTED:
        score = 0.55
        extra = context.get("imported_total", 1)
        # +0.1 per additional image beyond the first (max bonus 0.30)
        score += min(0.10 * max(extra - 1, 0), 0.30)

    elif source == AssetSource.AI_GENERATED:
        score = 0.80
        # If URL looks reachable, give a small bonus
        if url.startswith(("http://", "https://")):
            score += 0.10

    else:
        score = 0.50

    return min(score, 0.95)


def _build_inventory(state: AgentState) -> AssetInventory:
    """从 state 中盘点已有素材"""
    items: List[AssetItem] = []

    # 主图
    image_url = state.get("product_image_url")
    if image_url:
        items.append(AssetItem(
            asset_type=AssetType.MAIN_IMAGE,
            source=AssetSource.USER_PROVIDED,
            url=image_url,
            quality_score=_estimate_quality(image_url, AssetSource.USER_PROVIDED, {}),
        ))

    # 1688 搬运图片
    imported = state.get("imported_images", [])
    imported_context = {"imported_total": len(imported)}
    for url in imported:
        items.append(AssetItem(
            asset_type=AssetType.LIFESTYLE_IMAGE,
            source=AssetSource.IMPORTED,
            url=url,
            quality_score=_estimate_quality(url, AssetSource.IMPORTED, imported_context),
        ))

    # Studio 生成的场景图
    studio = state.get("studio_assets", {})
    if studio:
        scenes = studio.get("lifestyle_scenes", [])
        for scene in scenes:
            url = scene.get("image_url", "") if isinstance(scene, dict) else str(scene)
            items.append(AssetItem(
                asset_type=AssetType.LIFESTYLE_IMAGE,
                source=AssetSource.AI_GENERATED,
                url=url,
                quality_score=_estimate_quality(url, AssetSource.AI_GENERATED, {}),
            ))
        if studio.get("material_mode") == "source":
            # 搬运模式：主图已沿用
            if not any(i.asset_type == AssetType.MAIN_IMAGE for i in items):
                items.append(AssetItem(
                    asset_type=AssetType.MAIN_IMAGE,
                    source=AssetSource.IMPORTED,
                    quality_score=_estimate_quality("", AssetSource.IMPORTED, {}),
                ))

    # 视频
    video = state.get("video_package", {})
    if video and video.get("mode"):
        video_url = video.get("video_url", "")
        items.append(AssetItem(
            asset_type=AssetType.VIDEO,
            source=AssetSource.AI_GENERATED,
            url=video_url,
            quality_score=_estimate_quality(video_url, AssetSource.AI_GENERATED, {}),
        ))

    # 统计
    imported_count = sum(1 for i in items if i.source == AssetSource.IMPORTED)
    ai_count = sum(1 for i in items if i.source == AssetSource.AI_GENERATED)
    by_type = {}
    for item in items:
        by_type[item.asset_type.value] = by_type.get(item.asset_type.value, 0) + 1

    return AssetInventory(
        items=items,
        total_count=len(items),
        imported_count=imported_count,
        ai_generated_count=ai_count,
        by_type=by_type,
    )


def _analyze_gaps(
    inventory: AssetInventory,
    platform: str,
    intent: str,
) -> AssetGap:
    """分析素材缺口"""
    requirements = PLATFORM_ASSET_REQUIREMENTS.get(platform, PLATFORM_ASSET_REQUIREMENTS["Amazon"])
    existing_types = {item.asset_type for item in inventory.items}

    gaps: List[AssetGapItem] = []
    covered = []

    # 检查必需素材
    for asset_type in requirements["required"]:
        if asset_type in existing_types:
            covered.append(asset_type)
        else:
            cost = ASSET_COST_MAP.get(asset_type, {"credits": 5, "seconds": 10})
            gaps.append(AssetGapItem(
                asset_type=asset_type,
                priority="required",
                reason=f"{platform} 平台必需素材",
                suggested_action="ai_generate",
                estimated_cost_credits=cost["credits"],
                estimated_time_seconds=cost["seconds"],
            ))

    # 检查推荐素材（仅全链路上新时考虑）
    if intent == "full_launch":
        for asset_type in requirements["recommended"]:
            if asset_type in existing_types:
                covered.append(asset_type)
            else:
                cost = ASSET_COST_MAP.get(asset_type, {"credits": 5, "seconds": 10})
                gaps.append(AssetGapItem(
                    asset_type=asset_type,
                    priority="recommended",
                    reason=f"推荐补充以提升转化率",
                    suggested_action="ai_generate",
                    estimated_cost_credits=cost["credits"],
                    estimated_time_seconds=cost["seconds"],
                ))

    # 可选素材
    for asset_type in requirements.get("optional", []):
        if asset_type not in existing_types:
            cost = ASSET_COST_MAP.get(asset_type, {"credits": 5, "seconds": 10})
            gaps.append(AssetGapItem(
                asset_type=asset_type,
                priority="optional",
                reason="可选素材，按需生成",
                suggested_action="skip",
                estimated_cost_credits=cost["credits"],
                estimated_time_seconds=cost["seconds"],
            ))

    # 统计
    required_gaps = sum(1 for g in gaps if g.priority == "required")
    recommended_gaps = sum(1 for g in gaps if g.priority == "recommended")
    optional_gaps = sum(1 for g in gaps if g.priority == "optional")

    total_credits = sum(g.estimated_cost_credits for g in gaps if g.suggested_action != "skip")
    total_seconds = sum(g.estimated_time_seconds for g in gaps if g.suggested_action != "skip")

    # 策略判定
    if required_gaps == 0 and recommended_gaps == 0:
        strategy = "import_only"
        strategy_reasoning = "已有素材完全覆盖平台要求，无需 AI 生成"
    elif required_gaps == 0:
        strategy = "partial_ai"
        strategy_reasoning = "必需素材已覆盖，可选择性 AI 补充推荐素材"
    else:
        strategy = "full_ai"
        strategy_reasoning = f"存在 {required_gaps} 项必需素材缺口，需 AI 生成补充"

    return AssetGap(
        gaps=gaps,
        total_gaps=len(gaps),
        required_gaps=required_gaps,
        recommended_gaps=recommended_gaps,
        optional_gaps=optional_gaps,
        total_estimated_credits=total_credits,
        total_estimated_seconds=total_seconds,
        strategy=strategy,
        strategy_reasoning=strategy_reasoning,
        covered_types=covered,
    )


async def asset_inventory_node(state: AgentState) -> Dict[str, Any]:
    """素材盘点与缺口分析节点"""
    platform = state.get("target_platform", "Amazon")
    intent = state.get("user_intent", "full_launch")

    # 盘点已有素材
    inventory = _build_inventory(state)

    # 分析缺口
    gap = _analyze_gaps(inventory, platform, intent)

    # 计算素材完整度
    requirements = PLATFORM_ASSET_REQUIREMENTS.get(platform, PLATFORM_ASSET_REQUIREMENTS["Amazon"])
    all_needed = set(requirements["required"] + requirements["recommended"])
    existing_types = {item.asset_type for item in inventory.items}
    covered = all_needed & existing_types
    inventory.completeness_score = len(covered) / len(all_needed) if all_needed else 1.0

    trace_item = {
        "node": "asset_inventory",
        "status": "completed",
        "summary": (
            f"素材盘点: 已有 {inventory.total_count} 项（搬运 {inventory.imported_count}，"
            f"AI {inventory.ai_generated_count}），"
            f"缺口 {gap.total_gaps} 项（必需 {gap.required_gaps}），"
            f"策略: {gap.strategy}"
        ),
        "timestamp": time.time(),
        "detail": {
            "inventory": inventory.model_dump(),
            "gap": gap.model_dump(),
        },
    }

    current_trace = state.get("trace", []) or []

    return {
        "asset_inventory": inventory.model_dump(),
        "asset_gap": gap.model_dump(),
        "current_node": "asset_inventory",
        "trace": current_trace + [trace_item],
    }
