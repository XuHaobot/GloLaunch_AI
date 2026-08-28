"""ChannelRegistry —— 发布通道注册中心。"""
from typing import Dict, List, Optional

from app.domain.enums import Platform
from app.channels.base import ChannelAdapter
from app.channels.amazon_sp import AmazonSPChannel
from app.channels.shopee import ShopeeChannel
from app.channels.tiktok_shop import TikTokShopChannel


class ChannelRegistry:
    """发布通道注册中心（单例）"""

    _instance: Optional["ChannelRegistry"] = None

    def __init__(self):
        self._channels: Dict[Platform, ChannelAdapter] = {}
        self._register_defaults()

    @classmethod
    def get_instance(cls) -> "ChannelRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _register_defaults(self):
        """注册所有内置发布通道"""
        self.register(AmazonSPChannel())
        self.register(ShopeeChannel())
        self.register(TikTokShopChannel())

    def register(self, channel: ChannelAdapter):
        """注册发布通道"""
        self._channels[channel.platform] = channel

    def get(self, platform: Platform) -> Optional[ChannelAdapter]:
        """获取指定平台的发布通道"""
        return self._channels.get(platform)

    def get_by_name(self, platform_name: str) -> Optional[ChannelAdapter]:
        """根据平台名称字符串获取通道"""
        try:
            platform = Platform(platform_name)
            return self._channels.get(platform)
        except ValueError:
            return None

    async def get_available_channels(self) -> List[ChannelAdapter]:
        """获取所有可用发布通道"""
        available = []
        for channel in self._channels.values():
            if await channel.is_available():
                available.append(channel)
        return available

    async def get_status(self) -> Dict[str, Dict[str, any]]:
        """获取所有发布通道状态"""
        status = {}
        for platform, channel in self._channels.items():
            available = await channel.is_available()
            status[platform.value] = {
                "name": channel.display_name,
                "available": available,
                "dry_run": channel.is_dry_run,
                "platform": platform.value,
            }
        return status
