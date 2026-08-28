"""PublishPackage —— 发布包与人工审核（Human-in-the-loop）。

在最终发布前，将所有成果打包呈现给用户审核，
用户可逐项确认、修改或拒绝，实现真正的「人机协同」。
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from .enums import ComplianceStatus, PublishDecision
from .listing import ListingHealth
from .opportunity import OpportunityScore


class PublishCheckItem(BaseModel):
    """发布前检查项"""
    name: str
    status: ComplianceStatus
    details: str = ""
    auto_fixed: bool = False                    # 是否已自动修复


class PublishPackage(BaseModel):
    """发布包：汇总所有成果，等待人工审核"""

    # ── 基础信息 ──
    thread_id: str = ""
    sku: str = ""
    platform: str = ""
    market: str = ""
    created_at: float = 0.0

    # ── 发布内容快照 ──
    listing_snapshot: Dict[str, Any] = Field(default_factory=dict)   # Listing 内容快照
    assets_summary: Dict[str, Any] = Field(default_factory=dict)     # 素材清单摘要
    video_summary: Optional[Dict[str, Any]] = None                   # 视频摘要

    # ── 质量评估 ──
    listing_health: Optional[ListingHealth] = None
    opportunity_score: Optional[OpportunityScore] = None

    # ── 合规检查 ──
    compliance_status: ComplianceStatus = ComplianceStatus.PASS
    check_items: List[PublishCheckItem] = Field(default_factory=list)
    rule_check_results: List[Dict[str, Any]] = Field(default_factory=list)

    # ── 人工审核 ──
    review_decision: PublishDecision = PublishDecision.NEEDS_REVISION
    review_notes: str = ""                      # 用户审核备注
    reviewed_at: Optional[float] = None

    # ── 发布状态 ──
    ready_to_publish: bool = False
    published: bool = False
    published_at: Optional[float] = None
    publish_result: Optional[Dict[str, Any]] = None  # 平台返回结果

    # ── 导出 ──
    export_formats: List[str] = Field(default_factory=list)  # 支持的导出格式
    standard_feed_ready: bool = False           # 标准 feed 是否就绪
