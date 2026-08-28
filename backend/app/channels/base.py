"""ChannelAdapter 抽象基类 —— 发布通道统一接口。

与 ResearchSource（只读）相对，ChannelAdapter 负责「写」操作：
- 将 PublishPackage 发布到目标平台
- 执行平台特定的格式适配
- 管理发布状态与结果回报

设计原则：
- 读写分离：ChannelAdapter 只负责发布，不负责数据采集
- 可降级：凭证未配置时自动进入 dry_run 模式（模拟发布）
- 可审计：每次发布操作记录完整日志
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from app.domain.enums import Platform, ComplianceStatus
from app.domain.publish import PublishPackage


class ChannelAdapter(ABC):
    """发布通道抽象基类"""

    @property
    @abstractmethod
    def platform(self) -> Platform:
        """目标平台标识"""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """人类可读的平台名称"""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """检查发布通道是否可用（API 凭证是否配置）"""
        ...

    @property
    def is_dry_run(self) -> bool:
        """是否为模拟模式（凭证未配置或显式开启 dry_run）"""
        from app.config import get_settings
        return get_settings().publish_dry_run

    # ── 合规检查 ──

    @abstractmethod
    async def check_compliance(
        self,
        listing_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        执行平台合规检查。
        返回合规结果字典，包含 compliance_status 和 rule_check_results。
        """
        ...

    # ── 格式适配 ──

    @abstractmethod
    async def adapt_format(
        self,
        listing_data: Dict[str, Any],
        assets: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        将通用 Listing 数据转换为目标平台要求的格式。
        不同平台有不同的字段规范、字符限制、图片要求。
        """
        ...

    # ── 发布 ──

    @abstractmethod
    async def publish(
        self,
        package: PublishPackage,
    ) -> Dict[str, Any]:
        """
        执行发布操作。
        返回发布结果，包含 success、listing_id、errors 等。
        dry_run 模式下返回模拟结果。
        """
        ...

    # ── 状态查询 ──

    async def get_listing_status(self, listing_id: str) -> Optional[Dict[str, Any]]:
        """查询已发布 Listing 的状态（可选实现）"""
        return None

    async def update_listing(
        self,
        listing_id: str,
        updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        """更新已发布的 Listing（可选实现）"""
        return {"success": False, "error": "Not implemented"}
