"""Shopee 发布通道骨架。"""
from typing import Any, Dict, Optional

from app.domain.enums import Platform
from app.domain.publish import PublishPackage
from app.channels.base import ChannelAdapter


class ShopeeChannel(ChannelAdapter):
    """Shopee 发布通道"""

    @property
    def platform(self) -> Platform:
        return Platform.SHOPEE

    @property
    def display_name(self) -> str:
        return "Shopee Partner API"

    async def is_available(self) -> bool:
        from app.config import get_settings
        s = get_settings()
        return bool(s.shopee_partner_id and s.shopee_partner_key)

    async def check_compliance(self, listing_data: Dict[str, Any]) -> Dict[str, Any]:
        # TODO: 实现 Shopee 合规检查
        return {
            "compliance_status": "PASS",
            "rule_check_results": [
                {"rule_name": "Shopee Title Check", "status": "PASS", "details": "标题合规"},
            ],
        }

    async def adapt_format(
        self,
        listing_data: Dict[str, Any],
        assets: Dict[str, Any],
    ) -> Dict[str, Any]:
        # TODO: 实现 Shopee 格式适配
        return listing_data

    async def publish(self, package: PublishPackage) -> Dict[str, Any]:
        if self.is_dry_run or not await self.is_available():
            return {
                "success": True,
                "dry_run": True,
                "listing_id": f"DRY-SHOPEE-{package.sku or 'UNKNOWN'}",
                "message": "模拟发布成功（dry_run 模式）",
                "platform": "Shopee",
            }
        # TODO: 实现 Shopee Partner API 发布
        return {"success": False, "error": "Shopee 发布尚未实现", "platform": "Shopee"}
