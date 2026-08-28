"""发布通道层 —— ChannelAdapter 统一接口与各平台实现。"""
from .base import ChannelAdapter
from .amazon_sp import AmazonSPChannel
from .shopee import ShopeeChannel
from .tiktok_shop import TikTokShopChannel
from .registry import ChannelRegistry

__all__ = [
    "ChannelAdapter",
    "AmazonSPChannel",
    "ShopeeChannel",
    "TikTokShopChannel",
    "ChannelRegistry",
]
