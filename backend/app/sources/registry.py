"""SourceRegistry —— 数据源注册中心与智能路由。

负责：
1. 管理所有 ResearchSource 实例
2. 根据平台/可用性自动选择最佳数据源
3. 提供降级链：JustOneAPI → 平台直连 → LLM 兜底
"""
from typing import Dict, List, Optional, Type

from app.domain.enums import DataSourceType, Platform
from app.sources.base import ResearchSource
from app.sources.alibaba_1688 import Alibaba1688Source
from app.sources.amazon_research import AmazonResearchSource
from app.sources.shopee_research import ShopeeResearchSource
from app.sources.tiktok_research import TikTokResearchSource
from app.sources.temu_research import TemuResearchSource
from app.sources.justone import JustOneAPISource


class SourceRegistry:
    """数据源注册中心（单例）"""

    _instance: Optional["SourceRegistry"] = None

    def __init__(self):
        self._sources: Dict[DataSourceType, ResearchSource] = {}
        self._register_defaults()

    @classmethod
    def get_instance(cls) -> "SourceRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _register_defaults(self):
        """注册所有内置数据源"""
        self.register(Alibaba1688Source())
        self.register(AmazonResearchSource())
        self.register(ShopeeResearchSource())
        self.register(TikTokResearchSource())
        self.register(TemuResearchSource())
        self.register(JustOneAPISource())

    def register(self, source: ResearchSource):
        """注册数据源"""
        self._sources[source.source_type] = source

    def get(self, source_type: DataSourceType) -> Optional[ResearchSource]:
        """获取指定数据源"""
        return self._sources.get(source_type)

    def get_all(self) -> List[ResearchSource]:
        """获取所有已注册数据源"""
        return list(self._sources.values())

    async def get_available_sources(self) -> List[ResearchSource]:
        """获取所有可用数据源"""
        available = []
        for source in self._sources.values():
            if await source.is_available():
                available.append(source)
        return available

    async def get_best_source_for_platform(
        self,
        platform: str,
    ) -> Optional[ResearchSource]:
        """
        根据目标平台获取最佳数据源。
        优先级：JustOneAPI（若可用）→ 平台直连源
        """
        platform_type_map = {
            Platform.AMAZON: DataSourceType.AMAZON,
            Platform.SHOPEE: DataSourceType.SHOPEE,
            Platform.TIKTOK: DataSourceType.TIKTOK_SHOP,
            Platform.TEMU: DataSourceType.TEMU,
        }

        # 优先尝试 JustOneAPI
        justone = self._sources.get(DataSourceType.JUSTONEAPI)
        if justone and await justone.is_available():
            return justone

        # 回退到平台直连源
        target_type = platform_type_map.get(platform)
        if target_type:
            source = self._sources.get(target_type)
            if source and await source.is_available():
                return source

        return None

    async def get_status(self) -> Dict[str, Dict[str, any]]:
        """获取所有数据源状态（供前端展示）"""
        status = {}
        for source_type, source in self._sources.items():
            available = await source.is_available()
            status[source_type.value] = {
                "name": source.display_name,
                "available": available,
                "type": source_type.value,
            }
        return status
