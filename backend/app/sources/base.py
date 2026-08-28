"""ResearchSource 抽象基类 —— 数据采集层统一接口。

所有「读」类数据源（1688 商品导入、Amazon 竞品分析、Shopee 趋势…）
均实现此接口，供 Agent 节点统一调用。

设计原则：
- 只读不写：ResearchSource 只负责数据采集，不执行发布/修改操作
- 可降级：每个数据源提供 is_available() 检查，不可用时自动降级
- 可组合：Agent 节点可同时调用多个 Source 聚合数据
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.domain.enums import DataSourceType
from app.domain.product_profile import ProductProfile
from app.domain.market_context import MarketContext


def _compute_confidence(
    data_dict: Dict[str, Any],
    required_fields: List[str],
    optional_fields: Optional[List[str]] = None,
) -> float:
    """根据数据字段完整性动态计算置信度。

    算法：
    - 每个必需字段存在且有值：+ required_weight（均分，总和 0.7）
    - 每个可选字段存在且有值：+ optional_weight（均分，总和 0.25）
    - 上限 0.95（永远不声称 100% 置信）
    - 下限 0.1（只要有任意数据返回）

    Args:
        data_dict: 原始数据字典
        required_fields: 必需字段名列表
        optional_fields: 可选字段名列表（默认空）
    """
    optional_fields = optional_fields or []

    if not required_fields:
        return 0.1

    # 检查字段是否「有值」：非 None、非空字符串、非空列表/字典
    def _is_present(d: Dict, key: str) -> bool:
        val = d.get(key)
        if val is None:
            return False
        if isinstance(val, str) and not val.strip():
            return False
        if isinstance(val, (list, dict)) and len(val) == 0:
            return False
        return True

    required_weight = 0.7 / len(required_fields)
    optional_weight = 0.25 / len(optional_fields) if optional_fields else 0.0

    score = 0.0
    for field in required_fields:
        if _is_present(data_dict, field):
            score += required_weight

    for field in optional_fields:
        if _is_present(data_dict, field):
            score += optional_weight

    # 下限 0.1（只要有任何数据）
    if score > 0:
        score = max(score, 0.1)

    # 上限 0.95
    return round(min(score, 0.95), 4)


class ResearchSource(ABC):
    """数据采集源抽象基类"""

    @property
    @abstractmethod
    def source_type(self) -> DataSourceType:
        """数据源类型标识"""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """人类可读的数据源名称"""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """检查数据源是否可用（凭证是否配置、网络是否可达）"""
        ...

    # ── 商品导入 ──

    @abstractmethod
    async def import_product(self, url_or_id: str) -> Optional[ProductProfile]:
        """
        从数据源导入商品数据，返回 ProductProfile。
        失败时返回 None（由调用方决定是否降级）。
        """
        ...

    # ── 市场数据采集 ──

    @abstractmethod
    async def fetch_market_data(
        self,
        category: str,
        market: str = "US",
        platform: str = "Amazon",
        keywords: Optional[List[str]] = None,
    ) -> Optional[MarketContext]:
        """
        采集市场数据（竞品、关键词、价格分布等）。
        返回 MarketContext，失败返回 None。
        """
        ...

    # ── 关键词研究 ──

    async def fetch_keywords(
        self,
        query: str,
        market: str = "US",
        platform: str = "Amazon",
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        关键词研究（搜索量、竞争度等）。
        默认实现返回空列表，子类按需覆写。
        """
        return []

    # ── 竞品分析 ──

    async def fetch_competitors(
        self,
        category: str,
        market: str = "US",
        platform: str = "Amazon",
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        采集竞品数据。
        默认实现返回空列表，子类按需覆写。
        """
        return []
