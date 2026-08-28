"""系统连接状态：供前端「连接」页展示各外部服务的启用/降级状态。"""
import os
from typing import Any, Dict, List
from fastapi import APIRouter

from app.config import get_settings
from app.services.media import _ffmpeg_exe

router = APIRouter(prefix="/api/system", tags=["系统连接"])

@router.get("/connections")
async def connections() -> Dict[str, Any]:
    """返回各外部连接的配置状态（前端连接页卡片渲染）"""
    s = get_settings()
    token_file = os.path.join(s.data_dir, "ali1688_token.json")
    ali_configured = bool(s.ali1688_app_key and s.ali1688_app_secret)
    ali_authorized = bool(s.ali1688_access_token) or os.path.exists(token_file)

    items: List[Dict[str, Any]] = [
        {
            "id": "bailian",
            "name": "阿里云百炼 · Model Router",
            "desc": "文本 / 生图 / TTS 统一走专属 Token Plan 网关",
            "configured": bool(s.model_router_api_key),
            "status_text": "专属 Key 已连接" if s.model_router_api_key else "未配置 API Key",
        },
        {
            "id": "justoneapi",
            "name": "JustOneAPI（聚合数据采集）",
            "desc": "Amazon / 1688 / Shopee / TikTok Shop 四源统一接口",
            "configured": bool(s.justoneapi_api_key),
            "status_text": "已连接" if s.justoneapi_api_key else "未配置 Token",
        },
        {
            "id": "ali1688",
            "name": "1688 开放平台（官方 API）",
            "desc": "商品导入官方通道；未配置或未授权时自动降级为页面抓取",
            "configured": ali_configured,
            "authorized": ali_authorized,
            "status_text": "已授权" if ali_authorized else ("已配置，待授权" if ali_configured else "未配置 AppKey"),
            "action_url": "/api/import/1688/oauth/start" if ali_configured else None,
        },
        {
            "id": "aitryon",
            "name": "AITryon 虚拟试穿（DashScope aitryon 模型）",
            "desc": "本地集成模块：衣物图 + 模特图 → AI 融合合成；复用模型网关 Key",
            "configured": bool(s.model_router_api_key),
            "status_text": "已就绪（复用模型网关）" if s.model_router_api_key else "需先配置模型网关 Key",
        },
        {
            "id": "amazon_sp",
            "name": "Amazon SP-API（直连发布）",
            "desc": "真实上架提交；未配置时自动走演练模式 (Dry Run)",
            "configured": bool(s.amazon_sp_api_client_id and s.amazon_sp_api_client_secret
                               and s.amazon_sp_api_refresh_token),
            "status_text": "已配置" if (s.amazon_sp_api_client_id and s.amazon_sp_api_refresh_token) else "演练模式",
        },
        {
            "id": "alimt",
            "name": "阿里云电商图翻",
            "desc": "详情图中文 → 目标语言图；未配置时降级 Qwen-VL 识别翻译",
            "configured": bool(s.alimt_access_key_id and s.alimt_access_key_secret),
            "status_text": "已启用" if (s.alimt_access_key_id and s.alimt_access_key_secret) else "VL 兜底模式",
        },
        {
            "id": "ffmpeg",
            "name": "ffmpeg（视频合成）",
            "desc": "带货视频成片合成（系统 PATH 或 imageio-ffmpeg 内置版）；缺失时降级故事板模式",
            "configured": bool(_ffmpeg_exe()),
            "status_text": "已就绪" if _ffmpeg_exe() else "未检测到",
        },
    ]
    return {"items": items}
