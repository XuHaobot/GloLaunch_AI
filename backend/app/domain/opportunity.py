"""OpportunityScore —— 商品上架机会评分（多维度）。

帮助卖家在「上新前」判断这个商品值不值得做，
而非盲目走完整个链路后才发现不值得。
"""
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class DimensionScore(BaseModel):
    """单维度评分"""
    name: str                     # 维度名称
    score: int = 0                # 0-100（默认 0，评分引擎计算后赋值）
    weight: float = 1.0           # 权重
    reasoning: str = ""           # 评分理由（可解释性）
    factors: List[str] = Field(default_factory=list)  # 影响因子


class PlatformRecommendation(BaseModel):
    """平台推荐"""
    platform: str
    suitability_score: int        # 0-100 适配度
    reasoning: str = ""
    estimated_monthly_revenue: Optional[str] = None
    key_advantages: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)


class OpportunityScore(BaseModel):
    """商品上架机会评分"""

    # ── 综合评分 ──
    overall_score: Optional[int] = None         # 加权总分 0-100，None 表示数据不足无法评分
    recommendation: str = ""                    # "强烈推荐" / "推荐" / "谨慎" / "不推荐" / "数据不足"

    # ── 数据可信度（P0 新增）──
    data_confidence: str = "low"                # "high" / "medium" / "low"
    data_completeness: float = 0.0              # 0.0-1.0 数据完整度
    data_sources_used: List[str] = Field(default_factory=list)  # 实际使用的数据源

    # ── 六维评分 ──
    market_demand: DimensionScore = Field(
        default_factory=lambda: DimensionScore(name="市场需求")
    )
    competition: DimensionScore = Field(
        default_factory=lambda: DimensionScore(name="竞争格局")
    )
    price_margin: DimensionScore = Field(
        default_factory=lambda: DimensionScore(name="价格利润空间")
    )
    supply_chain: DimensionScore = Field(
        default_factory=lambda: DimensionScore(name="供应链优势")
    )
    content_differentiation: DimensionScore = Field(
        default_factory=lambda: DimensionScore(name="内容差异化潜力")
    )
    compliance_risk: DimensionScore = Field(
        default_factory=lambda: DimensionScore(name="合规风险")
    )

    # ── 平台推荐 ──
    platform_recommendations: List[PlatformRecommendation] = Field(default_factory=list)
    best_fit_platform: str = ""               # 最推荐平台

    # ── Supply-Market Fit 判定 ──
    supply_market_fit: str = ""               # "high" / "medium" / "low"
    fit_reasoning: str = ""

    # ── 决策建议 ──
    go_no_go: str = "go"                      # "go" / "caution" / "no_go"
    action_items: List[str] = Field(default_factory=list)  # 建议行动项
