"""领域模型层 —— GloLaunch AI 核心数据结构。

提供平台无关的商品数字档案、市场数据、机会评分、
素材盘点、Listing 质量评分和发布包等 Pydantic 模型。
"""
from .enums import (
    Platform, Market, Intent, CategoryFamily,
    AssetType, AssetSource, ComplianceStatus,
    PublishDecision, DataSourceType,
)
from .product_profile import ProductProfile
from .market_context import MarketContext, CompetitorSnapshot, KeywordData
from .opportunity import OpportunityScore, DimensionScore, PlatformRecommendation
from .asset import AssetInventory, AssetItem, AssetGap, AssetGapItem
from .listing import ListingHealth, HealthDimension
from .publish import PublishPackage, PublishCheckItem

__all__ = [
    # Enums
    "Platform", "Market", "Intent", "CategoryFamily",
    "AssetType", "AssetSource", "ComplianceStatus",
    "PublishDecision", "DataSourceType",
    # Models
    "ProductProfile",
    "MarketContext", "CompetitorSnapshot", "KeywordData",
    "OpportunityScore", "DimensionScore", "PlatformRecommendation",
    "AssetInventory", "AssetItem", "AssetGap", "AssetGapItem",
    "ListingHealth", "HealthDimension",
    "PublishPackage", "PublishCheckItem",
]
