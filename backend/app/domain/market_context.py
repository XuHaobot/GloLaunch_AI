"""MarketContext —— 真实市场数据上下文。

替代原先纯 LLM 生成的市场洞察，优先从 ResearchSource 拉取真实数据，
LLM 仅负责在真实数据基础上做分析总结。
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CompetitorSnapshot(BaseModel):
    """竞品快照"""
    asin_or_id: str = ""
    title: str = ""
    price: Optional[float] = None
    currency: str = "USD"
    rating: Optional[float] = None
    review_count: int = 0
    monthly_sales_est: Optional[int] = None      # 预估月销量
    bsr_rank: Optional[int] = None               # Best Sellers Rank
    listing_url: str = ""


class KeywordData(BaseModel):
    """关键词数据"""
    keyword: str
    search_volume: Optional[int] = None          # 月搜索量
    competition: Optional[str] = None            # 竞争度 (low/medium/high)
    relevance_score: float = 0.0                 # 与本商品的相关度 (0-1)
    trend: Optional[str] = None                  # 趋势方向 (up/down/stable)


class MarketContext(BaseModel):
    """市场数据上下文（来自真实数据源 + LLM 分析）"""

    # ── 数据溯源 ──
    data_sources: List[str] = Field(default_factory=list)  # 数据来源列表
    data_freshness: str = ""                      # 数据时效（如 "2026-08"）

    # ── 市场规模与趋势 ──
    market_size_usd: Optional[float] = None       # 市场规模（美元）
    growth_rate_yoy: Optional[float] = None       # 同比增长率
    market_overview: str = ""                     # 趋势概述（LLM 总结）

    # ── 竞品格局 ──
    competitors: List[CompetitorSnapshot] = Field(default_factory=list)
    avg_competitor_price: Optional[float] = None
    price_distribution: Dict[str, int] = Field(default_factory=dict)  # 价格段 → 竞品数

    # ── 关键词 ──
    top_keywords: List[KeywordData] = Field(default_factory=list)
    high_converting_keywords: List[str] = Field(default_factory=list)

    # ── 客群画像 ──
    target_audience: str = ""
    buyer_pain_points: List[str] = Field(default_factory=list)
    buyer_preferences: List[str] = Field(default_factory=list)

    # ── 定价建议 ──
    recommended_price_range: str = ""             # 如 "$32.99 - $45.99"
    recommended_price_low: Optional[float] = None
    recommended_price_high: Optional[float] = None
    profit_margin_est: str = ""                   # 如 "55% - 68%"

    # ── 差异化 ──
    differentiation_angles: List[str] = Field(default_factory=list)

    # ── 选品置信度 ──
    launch_confidence_score: int = 0              # 0-100

    # ── 原始数据（保留供调试）──
    raw_data: Dict[str, Any] = Field(default_factory=dict)
