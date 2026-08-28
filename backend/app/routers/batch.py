"""多商品批量上新：CSV 导入解析 + SSE 批量流水线（逐商品执行 LangGraph 全链路）"""
import csv
import io
import json
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from app.agent.graph import get_agent_graph
from app.services.task_store import TaskStore

router = APIRouter(prefix="/api/batch", tags=["批量上新"])

# CSV 列名归一化映射（兼容中英文表头）
COLUMN_ALIASES = {
    "name": ["name", "title", "product", "message", "商品名称", "名称", "商品", "指令"],
    "image_url": ["image_url", "image", "img", "图片", "图片链接", "主图"],
    "platform": ["platform", "平台", "目标平台"],
    "market": ["market", "站点", "目标市场", "国家"],
}

def _normalize_row(raw: Dict[str, Any]) -> Dict[str, str]:
    row: Dict[str, str] = {}
    lowered = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
    for field, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if lowered.get(alias):
                row[field] = lowered[alias]
                break
    return row

@router.post("/preview")
async def preview_csv(file: UploadFile = File(...)):
    """解析上传的 CSV 文件，返回归一化后的商品行供前端预览确认"""
    content = await file.read()
    for encoding in ("utf-8-sig", "gbk"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        return {"status": "error", "detail": "CSV 编码无法识别，请使用 UTF-8 或 GBK 编码"}

    try:
        reader = csv.DictReader(io.StringIO(text))
        rows = [_normalize_row(r) for r in reader]
    except Exception as e:
        return {"status": "error", "detail": f"CSV 解析失败: {e}"}

    items = [r for r in rows if r.get("name") or r.get("image_url")]
    return {
        "status": "success",
        "total": len(items),
        "items": items[:50],  # 单次批量上限 50 个商品
        "columns_hint": "支持列：商品名称/图片链接/平台/市场（中英文表头均可）",
    }

class BatchItem(BaseModel):
    name: str = ""
    image_url: Optional[str] = None
    platform: Optional[str] = "Amazon"
    market: Optional[str] = "US"

class BatchRunRequest(BaseModel):
    items: List[BatchItem]
    intent: Optional[str] = "full_launch"

def _sse(event: str, payload: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

@router.post("/run")
async def run_batch(req: BatchRunRequest):
    """SSE 批量流水线：逐商品执行上新任务并实时推送进度"""
    items = req.items[:50]
    intent = req.intent or "full_launch"

    async def event_generator() -> AsyncGenerator[str, None]:
        graph = get_agent_graph()
        store = TaskStore.get_instance()
        started_at = time.time()
        success_count = 0
        failed_count = 0

        yield _sse("batch_plan", {"total": len(items), "intent": intent})

        for index, item in enumerate(items):
            thread_id = str(uuid.uuid4())
            label = item.name or item.image_url or f"商品 #{index + 1}"
            yield _sse("item_start", {"index": index, "thread_id": thread_id, "name": label})

            try:
                config = {"configurable": {"thread_id": thread_id}}
                initial_state = {
                    "messages": [HumanMessage(content=f"批量上新：{label}")],
                    "user_intent": intent,
                    "target_platform": item.platform or "Amazon",
                    "target_market": item.market or "US",
                    "product_image_url": item.image_url,
                    "imported_images": [],
                    "trace": [],
                }
                async for _ in graph.astream(initial_state, config=config, stream_mode="updates"):
                    pass  # 批量模式只关心商品级进度，不推送节点级事件

                snapshot = graph.get_state(config)
                values = snapshot.values if snapshot else {}
                attrs = values.get("product_attributes") or {}
                listing = values.get("listing_content") or {}

                result = {
                    "product_attributes": attrs,
                    "market_insights": values.get("market_insights"),
                    "trend_benchmark": values.get("trend_benchmark"),
                    "listing_content": listing,
                    "studio_assets": values.get("studio_assets"),
                    "video_package": values.get("video_package"),
                    "localized_images": values.get("localized_images"),
                    "platform_package": values.get("platform_package"),
                    "trace": values.get("trace", []),
                }
                store.save_task(
                    thread_id, result,
                    platform=item.platform or "", market=item.market or "",
                    intent=intent, message=f"[批量] {label}",
                )
                try:
                    store.save_version(
                        thread_id, listing,
                        category=attrs.get("category", ""),
                        platform=item.platform or "", market=item.market or "",
                    )
                except Exception:
                    pass

                success_count += 1
                yield _sse("item_complete", {
                    "index": index, "thread_id": thread_id, "status": "success",
                    "category": attrs.get("category", ""),
                    "title": listing.get("title", "")[:120],
                })
            except Exception as e:
                failed_count += 1
                yield _sse("item_error", {"index": index, "thread_id": thread_id, "error": str(e)[:200]})

        yield _sse("batch_complete", {
            "total": len(items),
            "success": success_count,
            "failed": failed_count,
            "elapsed_seconds": round(time.time() - started_at, 1),
        })

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
