"""ListingHealth —— Listing 质量评分模型。

在 Listing 生成后、发布前进行质量评估，
给出可操作的改进建议，而非简单的 PASS/FAIL。
"""
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from .enums import ComplianceStatus


class HealthDimension(BaseModel):
    """单维度评分"""
    name: str
    score: int                    # 0-100
    status: ComplianceStatus = ComplianceStatus.PASS
    details: str = ""
    suggestions: List[str] = Field(default_factory=list)


class ListingHealth(BaseModel):
    """Listing 综合质量评分"""

    # ── 综合评分 ──
    overall_score: int = 0                    # 0-100
    grade: str = ""                           # A/B/C/D/F
    status: ComplianceStatus = ComplianceStatus.PASS

    # ── 八维评分 ──
    title_health: HealthDimension = Field(
        default_factory=lambda: HealthDimension(name="标题质量")
    )
    bullets_health: HealthDimension = Field(
        default_factory=lambda: HealthDimension(name="五点描述")
    )
    description_health: HealthDimension = Field(
        default_factory=lambda: HealthDimension(name="商品描述")
    )
    images_health: HealthDimension = Field(
        default_factory=lambda: HealthDimension(name="图片素材")
    )
    keywords_health: HealthDimension = Field(
        default_factory=lambda: HealthDimension(name="关键词覆盖")
    )
    attributes_health: HealthDimension = Field(
        default_factory=lambda: HealthDimension(name="属性完整度")
    )
    category_health: HealthDimension = Field(
        default_factory=lambda: HealthDimension(name="类目匹配")
    )
    compliance_health: HealthDimension = Field(
        default_factory=lambda: HealthDimension(name="合规检查")
    )

    # ── 平台适配度 ──
    platform: str = ""
    platform_fit_score: int = 0               # 与目标平台的适配度 0-100

    # ── 改进建议（按优先级排序）──
    improvement_priorities: List[str] = Field(default_factory=list)

    # ── 与竞品对比 ──
    vs_competitor_avg: Optional[str] = None   # 如 "高于竞品平均 15%"
