"""平台直连发布：一键将上新成果发布至电商平台（OAuth 凭证配置后真实上架，否则演练模式）"""
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.publisher import publish_package

router = APIRouter(prefix="/api/publish", tags=["平台直连发布"])

class PublishRequest(BaseModel):
    thread_id: str
    platform: Optional[str] = None  # 不传则沿用任务原平台
    dry_run: Optional[bool] = None  # 不传则取服务端 publish_dry_run 配置

@router.post("")
async def publish(req: PublishRequest):
    """执行发布，返回发布回执（mode: live / simulated）"""
    try:
        payload = await publish_package(req.thread_id, req.platform, req.dry_run)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "success", **payload}
