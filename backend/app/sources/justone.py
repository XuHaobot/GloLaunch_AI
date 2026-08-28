"""JustOneAPI 统一数据采集源 —— 第三方聚合平台接入预留位。

JustOneAPI (https://docs.justoneapi.com/zh/) 提供 1688、Amazon、Shopee、
TikTok Shop、Temu 等多平台统一 API 接入。

当前为架构预留，不实际集成。配置 justoneapi_api_key 后自动启用，
作为各平台数据源的底层通道。
"""
from typing import Any, Dict, List, Optional

from app.domain.enums import DataSourceType
from app.domain.product_profile import ProductProfile
from app.domain.market_context import MarketContext
from app.sources.base import ResearchSource


class JustOneAPISource(ResearchSource):
    """
    JustOneAPI 统一数据采集入口。

    架构定位：
    - 作为 ResearchSource 的一种实现，对外暴露统一接口
    - 内部根据 platform 参数路由到 JustOneAPI 的不同端点
    - 当 JustOneAPI 不可用时，各平台 Source 回退到各自的直连实现

    接入步骤（未来）：
    1. 在 .env 中配置 JUSTONEAPI_API_KEY 和 JUSTONEAPI_BASE_URL
    2. 实现 _call_api() 方法中的 HTTP 调用逻辑
    3. 在 SourceRegistry 中注册为高优先级数据源
    """

    @property
    def source_type(self) -> DataSourceType:
        return DataSourceType.JUSTONEAPI

    @property
    def display_name(self) -> str:
        return "JustOneAPI 聚合数据"

    async def is_available(self) -> bool:
        from app.config import get_settings
        s = get_settings()
        return bool(getattr(s, "justoneapi_api_key", ""))

    async def import_product(
        self,
        url_or_id: str,
        platform: str = "1688",
    ) -> Optional[ProductProfile]:
        """
        通过 JustOneAPI 导入商品。

        Args:
            url_or_id: 商品 URL 或 ID
            platform: 来源平台 (1688/amazon/shopee/tiktok/temu)
        """
        if not await self.is_available():
            return None
        # TODO: 实现 JustOneAPI 商品导入调用
        return None

    async def fetch_market_data(
        self,
        category: str,
        market: str = "US",
        platform: str = "Amazon",
        keywords: Optional[List[str]] = None,
    ) -> Optional[MarketContext]:
        """通过 JustOneAPI 获取市场数据"""
        if not await self.is_available():
            return None
        # TODO: 实现 JustOneAPI 市场数据调用
        return None

    async def fetch_keywords(
        self,
        query: str,
        market: str = "US",
        platform: str = "Amazon",
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """通过 JustOneAPI 进行关键词研究"""
        if not await self.is_available():
            return []
        # TODO: 实现 JustOneAPI 关键词调用
        return []

    async def fetch_competitors(
        self,
        category: str,
        market: str = "US",
        platform: str = "Amazon",
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """通过 JustOneAPI 采集竞品数据"""
        if not await self.is_available():
            return []
        # TODO: 实现 JustOneAPI 竞品采集
        return []
