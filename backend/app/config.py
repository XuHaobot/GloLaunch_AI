import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # API 接口网关（密钥仅存放于 .env，严禁硬编码进源码）
    model_router_api_key: str = ""
    model_router_base_url: str = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"

    # 模型名称（Token Plan 团队版，无需 qwen/ 前缀）
    model_text_flagship: str = "qwen3.8-max"   # 市场洞察与深度推理（旗舰）
    model_text_plus: str = "qwen3.7-plus"      # Listing文案（多模态）
    model_text_flash: str = "qwen3.6-flash"    # 快速校验与适配（快速）
    model_vl: str = "qwen3.7-plus"             # 多模态视觉属性提取与图片文字识别/翻译兜底（套餐无独立 VL 模型）
    model_image: str = "wan2.7-image-pro"      # AI 场景图/白底主图生成（同步调用）
    model_image_edit: str = "wan2.5-i2i-preview"  # 图片编辑（异步任务）用于真实试穿合成；套餐未包含时自动降级预设兜底
    model_tts: str = "qwen-audio-3.0-tts-plus"    # 商品展示视频自动配音（TTS 语音合成）
    tts_voice: str = "longanhuan_v3.6"            # TTS 音色（Qwen-Audio-TTS 系列音色，支持中英文）

    # aitryon 虚拟试穿已集成为本地模块（app/services/aitryon.py），
    # 复用 model_router_api_key 访问 DashScope，无需额外配置。

    # 1688 开放平台官方 API（稳定导入通道，替代反爬不稳定的页面抓取）。
    # 三项凭证齐全时优先走官方 API，未配置或调用失败时自动降级为页面抓取。
    ali1688_app_key: str = ""
    ali1688_app_secret: str = ""
    ali1688_access_token: str = ""
    ali1688_gateway: str = "https://gw.open.1688.com/openapi"
    # OAuth 授权回调地址（需与开放平台应用里登记的回调地址一致）
    ali1688_redirect_uri: str = "http://localhost:5173/api/import/1688/oauth/callback"

    # 电商平台 OAuth 直连发布凭证（未配置时自动走模拟发布/演练模式）
    publish_dry_run: bool = True
    amazon_sp_api_client_id: str = ""
    amazon_sp_api_client_secret: str = ""
    amazon_sp_api_refresh_token: str = ""
    shopee_partner_id: str = ""
    shopee_partner_key: str = ""

    # 阿里云电商图片翻译（识图翻译）：详情页中文图 → 目标语言图。
    # 未配置 AK/SK 时，节点自动降级为 Qwen-VL 文字识别+翻译方案。
    alimt_access_key_id: str = ""
    alimt_access_key_secret: str = ""
    alimt_region_id: str = "cn-hangzhou"
    alimt_endpoint: str = "mt.cn-hangzhou.aliyuncs.com"

    # JustOneAPI 第三方聚合数据平台（https://docs.justoneapi.com/zh/）
    # 支持 1688、Amazon、Shopee、TikTok Shop、Temu 多平台统一 API 接入。
    # 未配置时各数据源回退到各自的直连实现。
    justoneapi_api_key: str = ""
    justoneapi_base_url: str = "https://api.justoneapi.com"

    # 本地数据存储
    data_dir: str = "data"
    chroma_dir: str = "data/chroma"
    upload_dir: str = "uploads"
    sqlite_path: str = "data/glolaunch.db"
    checkpoint_path: str = "data/checkpoints.db"

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

@lru_cache()
def get_settings() -> Settings:
    return Settings()
