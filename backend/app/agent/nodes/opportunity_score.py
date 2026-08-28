"""opportunity_score_node —— 上架机会评分节点。

在商品属性提取和市场洞察完成后，
计算商品的上架机会评分，帮助卖家决定是否继续上新。
"""
import time
from typing import Dict, Any

from app.agent.state import AgentState
from app.domain.product_profile import ProductProfile
from app.domain.market_context import MarketContext, CompetitorSnapshot, KeywordData
from app.intelligence.opportunity_scorer import OpportunityScorer


def _build_product_profile(attrs: Dict[str, Any]) -> ProductProfile:
    """从 agent state 中的 product_attributes 构建 ProductProfile"""
    from app.domain.enums import CategoryFamily

    family_str = attrs.get("category_family", "general")
    try:
        family = CategoryFamily(family_str)
    except ValueError:
        family = CategoryFamily.GENERAL

    return ProductProfile(
        category_family=family,
        category=attrs.get("category", ""),
        title=attrs.get("title", ""),
        materials=attrs.get("materials", []),
        colors=attrs.get("colors", []),
        sizes=attrs.get("sizes", []),
        key_specs=attrs.get("key_specs", []),
        design_features=attrs.get("design_features", []),
        style_tags=attrs.get("style_tags", []),
        target_occasions=attrs.get("target_occasions", []),
        supply_price_cny=attrs.get("supply_price_cny"),
        moq=attrs.get("moq"),
        lead_time_days=attrs.get("lead_time_days"),
        supplier_id=attrs.get("supplier_id", ""),
        supplier_name=attrs.get("supplier_name", ""),
        original_images=attrs.get("original_images", []),
        main_image_url=attrs.get("main_image_url", ""),
        confidence=attrs.get("confidence", 0.0),
    )


def _build_market_context(insights: Dict[str, Any]) -> MarketContext:
    """从 agent state 中的 market_insights 构建 MarketContext
    支持真实竞品数据和关键词数据的映射。
    """
    ctx = MarketContext(
        data_sources=insights.get("data_sources", ["LLM + RAG"]),
        data_freshness=insights.get("data_freshness", ""),
        market_overview=insights.get("market_overview", ""),
        target_audience=insights.get("target_audience", ""),
        buyer_pain_points=insights.get("buyer_pain_points", []),
        differentiation_angles=insights.get("differentiation_angles", []),
        high_converting_keywords=insights.get("high_converting_keywords", []),
        recommended_price_range=insights.get("recommended_price_range", ""),
        profit_margin_est=insights.get("profit_margin_est", ""),
        launch_confidence_score=insights.get("launch_confidence_score", 0),
    )

    # ── 映射真实竞品数据 ──
    competitors_raw = insights.get("competitors", [])
    if competitors_raw:
        ctx.competitors = [
            CompetitorSnapshot(
                asin_or_id=c.get("asin", ""),
                title=c.get("title", ""),
                price=float(c["price"]) if c.get("price") else None,
                currency="USD",
                rating=float(c["rating"]) if c.get("rating") else None,
                review_count=int(c.get("review_count", 0)),
            )
            for c in competitors_raw[:15]
        ]
        # 计算真实均价
        prices = [c.price for c in ctx.competitors if c.price]
        if prices:
            ctx.avg_competitor_price = sum(prices) / len(prices)
            # 构建价格分布
            low = sum(1 for p in prices if p < 20)
            mid = sum(1 for p in prices if 20 <= p < 50)
            high = sum(1 for p in prices if p >= 50)
            ctx.price_distribution = {"<$20": low, "$20-50": mid, ">$50": high}
            # 基于竞品价格推算建议价格
            ctx.recommended_price_low = min(prices) if prices else None
            ctx.recommended_price_high = max(prices) if prices else None

    # ── 映射真实关键词数据 ──
    keywords_raw = insights.get("top_keywords", [])
    if keywords_raw:
        ctx.top_keywords = [
            KeywordData(
                keyword=kw.get("keyword", ""),
                search_volume=kw.get("search_volume"),
                competition=kw.get("competition"),
                relevance_score=kw.get("relevance_score", 0.5),
            )
            for kw in keywords_raw[:10]
        ]

    return ctx


async def opportunity_score_node(state: AgentState) -> Dict[str, Any]:
    """上架机会评分节点：评估商品值不值得做"""
    attrs = state.get("product_attributes", {})
    insights = state.get("market_insights", {})
    platform = state.get("target_platform", "Amazon")
    market = state.get("target_market", "US")

    product = _build_product_profile(attrs)
    market_ctx = _build_market_context(insights)

    scorer = OpportunityScorer()
    score = scorer.score(product, market_ctx, platform, market)

    score_str = (
        f"{score.overall_score}/100" if score.overall_score is not None
        else "数据不足"
    )
    trace_item = {
        "node": "opportunity_score",
        "status": "completed" if score.overall_score is not None else "data_insufficient",
        "summary": (
            f"机会评分: {score_str} ({score.recommendation})，"
            f"数据可信度: {score.data_confidence}，"
            f"Supply-Market Fit: {score.supply_market_fit}，"
            f"建议: {score.go_no_go}"
        ),
        "timestamp": time.time(),
        "detail": score.model_dump(),
    }

    current_trace = state.get("trace", []) or []

    return {
        "opportunity_score": score.model_dump(),
        "current_node": "opportunity_score",
        "trace": current_trace + [trace_item],
    }
