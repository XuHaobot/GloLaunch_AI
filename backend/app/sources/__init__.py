"""数据采集源层 —— ResearchSource 统一接口与各平台实现。"""
from .base import ResearchSource
from .alibaba_1688 import Alibaba1688Source
from .amazon_research import AmazonResearchSource
from .shopee_research import ShopeeResearchSource
from .tiktok_research import TikTokResearchSource
from .temu_research import TemuResearchSource
from .justone import JustOneAPISource
from .registry import SourceRegistry

__all__ = [
    "ResearchSource",
    "Alibaba1688Source",
    "AmazonResearchSource",
    "ShopeeResearchSource",
    "TikTokResearchSource",
    "TemuResearchSource",
    "JustOneAPISource",
    "SourceRegistry",
]
