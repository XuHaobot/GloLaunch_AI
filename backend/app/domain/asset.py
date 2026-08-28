"""AssetInventory & AssetGap —— 素材盘点与缺口分析。

核心理念：「搬运优先，AI 按需补给」
先盘点已有素材，识别缺失项，仅对缺口触发 AI 生成，
避免重复生产、节省额度和时间。
"""
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from .enums import AssetSource, AssetType


class AssetItem(BaseModel):
    """单项素材"""
    asset_type: AssetType
    source: AssetSource
    url: str = ""
    quality_score: Optional[float] = None       # 质量评分 0-1
    localization_status: str = "none"           # none / pending / done
    notes: str = ""


class AssetInventory(BaseModel):
    """素材盘点清单：已有素材的完整清单"""

    items: List[AssetItem] = Field(default_factory=list)
    total_count: int = 0
    imported_count: int = 0                     # 搬运素材数
    ai_generated_count: int = 0                 # AI 生成素材数

    # 按类型统计
    by_type: Dict[str, int] = Field(default_factory=dict)

    # 素材完整度评估
    completeness_score: float = 0.0             # 0-1，各平台要求的素材覆盖率


class AssetGapItem(BaseModel):
    """单项素材缺口"""
    asset_type: AssetType
    priority: str = "required"                  # required / recommended / optional
    reason: str = ""                            # 为什么需要这个素材
    suggested_action: str = ""                  # "ai_generate" / "user_provide" / "skip"
    estimated_cost_credits: int = 0             # 预估消耗积分
    estimated_time_seconds: int = 0             # 预估生成耗时


class AssetGap(BaseModel):
    """素材缺口分析结果"""

    gaps: List[AssetGapItem] = Field(default_factory=list)
    total_gaps: int = 0
    required_gaps: int = 0
    recommended_gaps: int = 0
    optional_gaps: int = 0

    # 成本预估
    total_estimated_credits: int = 0
    total_estimated_seconds: int = 0

    # 策略建议
    strategy: str = ""                          # "full_ai" / "partial_ai" / "import_only"
    strategy_reasoning: str = ""

    # 可跳过的项（搬运已覆盖）
    covered_types: List[AssetType] = Field(default_factory=list)
