"""共享枚举定义"""
from enum import Enum


class Platform(str, Enum):
    """目标销售平台"""
    AMAZON = "Amazon"
    SHOPEE = "Shopee"
    TIKTOK = "TikTok"
    TEMU = "Temu"


class Market(str, Enum):
    """目标市场/站点"""
    US = "US"
    EU = "EU"
    SOUTHEAST_ASIA = "Southeast Asia"
    JP = "JP"
    KR = "KR"
    UK = "UK"
    DE = "DE"
    FR = "FR"


class Intent(str, Enum):
    """用户意图"""
    FULL_LAUNCH = "full_launch"
    MARKET_ONLY = "market_only"
    LISTING_ONLY = "listing_only"


class CategoryFamily(str, Enum):
    """品类大类"""
    APPAREL = "apparel"
    SHOES = "shoes"
    BAGS = "bags"
    ACCESSORIES = "accessories"
    HOME = "home"
    BEAUTY = "beauty"
    ELECTRONICS = "electronics"
    GENERAL = "general"


class AssetType(str, Enum):
    """素材类型"""
    MAIN_IMAGE = "main_image"           # 主图
    LIFESTYLE_IMAGE = "lifestyle_image" # 场景图
    INFOGRAPHIC = "infographic"         # 信息图/卖点图
    SIZE_CHART = "size_chart"           # 尺码表
    VIDEO = "video"                     # 商品视频
    A_PLUS_CONTENT = "a_plus_content"   # A+ 图文
    PACKAGING = "packaging"             # 包装图


class AssetSource(str, Enum):
    """素材来源"""
    IMPORTED = "imported"       # 从供应商/1688 搬运
    AI_GENERATED = "ai"         # AI 生成
    USER_PROVIDED = "user"      # 用户自行提供
    PLACEHOLDER = "placeholder" # 占位（待补充）


class ComplianceStatus(str, Enum):
    """合规状态"""
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"


class PublishDecision(str, Enum):
    """人工审核决策"""
    APPROVED = "approved"           # 通过，可发布
    NEEDS_REVISION = "needs_revision"  # 需修改
    REJECTED = "rejected"           # 拒绝


class DataSourceType(str, Enum):
    """数据来源类型（ResearchSource 用）"""
    ALIBABA_1688 = "1688"
    AMAZON = "amazon"
    SHOPEE = "shopee"
    TIKTOK_SHOP = "tiktok_shop"
    TEMU = "temu"
    JUSTONEAPI = "justoneapi"
