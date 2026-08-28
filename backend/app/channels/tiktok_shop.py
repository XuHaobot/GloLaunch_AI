"""TikTok Shop 发布通道骨架。"""
from typing import Any, Dict, Optional

from app.domain.enums import Platform
from app.domain.publish import PublishPackage
from app.channels.base import ChannelAdapter


class TikTokShopChannel(ChannelAdapter):
    """TikTok Shop 发布通道"""

    @property
    def platform(self) -> Platform:
        return Platform.TIKTOK

    @property
    def display_name(self) -> str:
        return "TikTok Shop API"

    async def is_available(self) -> bool:
        # TODO: 检查 TikTok Shop API 凭证
        return False

    async def check_compliance(self, listing_data: Dict[str, Any]) -> Dict[str, Any]:
        # TODO: 实现 TikTok Shop 合规检查
        return {
            "compliance_status": "PASS",
            "rule_check_results": [],
        }

    async def adapt_format(
        self,
        listing_data: Dict[str, Any],
        assets: Dict[str, Any],
    ) -> Dict[str, Any]:
        # TODO: 实现 TikTok Shop 格式适配
        return listing_data

    async def publish(self, package: PublishPackage) -> Dict[str, Any]:
        return {
            "success": True,
            "dry_run": True,
            "listing_id": f"DRY-TIKTOK-{package.sku or 'UNKNOWN'}",
            "message": "模拟发布成功（dry_run 模式）",
            "platform": "TikTok Shop",
        }
