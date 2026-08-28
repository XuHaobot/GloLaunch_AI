"""V2 API 路由 —— 数据源状态、发布审核、Listing Health 等。"""
import time
import uuid
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.domain.enums import PublishDecision
from app.sources.registry import SourceRegistry
from app.channels.registry import ChannelRegistry
from app.services.task_store import TaskStore

router = APIRouter(prefix="/api/v2", tags=["V2 架构接口"])


# ── 数据源状态 ──

@router.get("/sources/status")
async def get_sources_status():
    """获取所有数据采集源的状态（可用性）"""
    registry = SourceRegistry.get_instance()
    return await registry.get_status()


# ── 发布通道状态 ──

@router.get("/channels/status")
async def get_channels_status():
    """获取所有发布通道的状态（可用性、dry_run 模式）"""
    registry = ChannelRegistry.get_instance()
    return await registry.get_status()


# ── 发布审核 ──

class ReviewRequest(BaseModel):
    """人工审核请求"""
    thread_id: str
    decision: str  # "approved" / "needs_revision" / "rejected"
    notes: str = ""


@router.post("/publish/review")
async def submit_publish_review(req: ReviewRequest):
    """
    提交人工审核结果。
    用户在前端审核 PublishPackage 后，将审核决策提交至此。
    审核结果会回写到 TaskStore 中的 publish_package。
    """
    try:
        decision = PublishDecision(req.decision)
    except ValueError:
        raise HTTPException(400, f"无效的审核决策: {req.decision}")

    store = TaskStore.get_instance()
    task = store.get_task(req.thread_id)
    if not task:
        raise HTTPException(404, f"任务不存在: {req.thread_id}")

    result = task.get("result", {})
    publish_pkg = result.get("publish_package", {})
    if not publish_pkg:
        raise HTTPException(400, "该任务尚未生成发布包")

    # 回写审核决策
    publish_pkg["review_decision"] = decision.value
    publish_pkg["review_notes"] = req.notes
    publish_pkg["reviewed_at"] = time.time()
    publish_pkg["reviewed"] = True

    # 根据决策更新 ready_to_publish
    if decision == PublishDecision.APPROVED:
        publish_pkg["ready_to_publish"] = True
    elif decision == PublishDecision.REJECTED:
        publish_pkg["ready_to_publish"] = False

    # 回写 TaskStore
    result["publish_package"] = publish_pkg
    store.save_task(
        thread_id=req.thread_id,
        result=result,
        platform=task.get("platform", ""),
        market=task.get("market", ""),
        intent=task.get("intent", ""),
        message=task.get("message", ""),
    )

    return {
        "thread_id": req.thread_id,
        "decision": decision.value,
        "notes": req.notes,
        "status": "updated",
        "ready_to_publish": publish_pkg.get("ready_to_publish", False),
    }


class ExportPackageRequest(BaseModel):
    """导出发布包请求"""
    thread_id: str
    format: str = "json"  # json / csv


@router.post("/publish/execute")
async def execute_publish(req: ExportPackageRequest):
    """
    执行发布（审核通过后调用）。
    从 TaskStore 加载 publish_package，导出为标准格式，
    并记录发布日志。真实平台 API 发布待接入。
    """
    store = TaskStore.get_instance()
    task = store.get_task(req.thread_id)
    if not task:
        raise HTTPException(404, f"任务不存在: {req.thread_id}")

    result = task.get("result", {})
    publish_pkg = result.get("publish_package", {})
    if not publish_pkg:
        raise HTTPException(400, "该任务尚未生成发布包")

    # 检查审核状态
    if publish_pkg.get("review_decision") != PublishDecision.APPROVED.value:
        raise HTTPException(400, "发布包尚未通过审核，无法执行发布")

    # 组装导出包
    export_package = {
        "publish_id": f"PUB-{uuid.uuid4().hex[:12].upper()}",
        "thread_id": req.thread_id,
        "platform": publish_pkg.get("platform", task.get("platform", "")),
        "market": publish_pkg.get("market", task.get("market", "")),
        "sku": publish_pkg.get("sku", ""),
        "listing": result.get("listing_content", {}),
        "assets": publish_pkg.get("assets_summary", {}),
        "opportunity_score": result.get("opportunity_score", {}),
        "listing_health": result.get("listing_health", {}),
        "exported_at": time.time(),
        "export_format": req.format,
    }

    # 记录发布日志
    store.save_publish(
        publish_id=export_package["publish_id"],
        thread_id=req.thread_id,
        platform=export_package["platform"],
        market=export_package["market"],
        mode="export",
        status="exported",
        report=export_package,
    )

    return {
        "publish_id": export_package["publish_id"],
        "thread_id": req.thread_id,
        "status": "exported",
        "package": export_package,
        "message": "发布包已导出，真实平台发布待接入 API",
    }
