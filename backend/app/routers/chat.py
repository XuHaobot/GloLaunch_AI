import json
import asyncio
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import HumanMessage

from app.agent.graph import get_agent_graph
from app.agent.pipeline_meta import (
    PIPELINE_NODES, OPTIONAL_NODES, build_plan, estimate_remaining_eta,
)
from app.services.task_store import TaskStore

router = APIRouter(prefix="/api/chat", tags=["Agent 智能对话"])

VALID_INTENTS = ("full_launch", "market_only", "listing_only")

class LaunchRequest(BaseModel):
    message: str = ""
    product_image_url: Optional[str] = None
    imported_images: Optional[List[str]] = None  # 1688 搬运带入的详情图（供图片本地化）
    target_platform: Optional[str] = "Amazon"
    target_market: Optional[str] = "US"
    intent: Optional[str] = "full_launch"
    disabled_stages: Optional[List[str]] = None  # 用户关闭的可选节点（hub 技能开关）
    thread_id: Optional[str] = None
    resume: Optional[bool] = False  # True 时携带原 thread_id 从断点续跑
    # ── 1688 导入的真实商品数据 ──
    product_title: Optional[str] = None          # 商品标题
    supply_price_cny: Optional[float] = None     # 供应价格（人民币）
    sku_attributes: Optional[Dict[str, List[str]]] = None  # SKU 属性（如 {颜色: [红,蓝], 尺码: [S,M,L]}）
    source_url: Optional[str] = None             # 来源链接

def _sse(event: str, payload: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

def _json_safe(obj: Any) -> Any:
    """递归将不可 JSON 序列化对象转为可序列化结构（LangChain 消息对象提取 content，其余 str 兜底）"""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if hasattr(obj, "content") and hasattr(obj, "type"):  # LangChain 消息对象
        return {"role": getattr(obj, "type", "ai"), "content": _json_safe(obj.content)}
    return str(obj)

class NodeLifecycleHandler(BaseCallbackHandler):
    """监听 LangGraph 节点生命周期，将 start/end 事件推入队列供 SSE 消费"""

    def __init__(self, queue: asyncio.Queue):
        self.queue = queue

    def _node_name(self, serialized: Optional[dict], kwargs: dict) -> Optional[str]:
        name = (serialized or {}).get("name") or kwargs.get("name")
        return name if name in PIPELINE_NODES else None

    def on_chain_start(self, serialized, inputs, *, run_id=None, **kwargs):
        name = self._node_name(serialized, kwargs)
        if name:
            self.queue.put_nowait({"type": "node_start", "node": name, "ts": time.time()})

    def on_chain_error(self, error, *, run_id=None, **kwargs):
        # 节点级错误（图执行异常会另行通过 astream 抛出）
        pass

@router.post("/stream")
async def chat_stream(req: LaunchRequest):
    """
    SSE 流式图执行接口（工作台协议）：
    - plan:        本次任务的执行计划（阶段泳道 + 预估耗时）
    - node_start:  节点开始执行（含实时进度与剩余 ETA）
    - node_update: 节点完成（含实际耗时、产出数据与进度）
    - complete:    全链路完成（含完整结果体）
    - error:       执行异常（前端可携带 thread_id + resume 断点续跑）
    """
    thread_id = req.thread_id or str(uuid.uuid4())
    intent = req.intent if req.intent in VALID_INTENTS else "full_launch"
    disabled = [n for n in (req.disabled_stages or []) if n in OPTIONAL_NODES]
    graph = get_agent_graph()

    async def event_generator() -> AsyncGenerator[str, None]:
        plan = build_plan(intent, disabled)
        planned_ids = [n["id"] for n in plan["nodes"]]
        completed: List[str] = []
        node_started_at: Dict[str, float] = {}

        yield _sse("plan", {"thread_id": thread_id, **plan})

        queue: asyncio.Queue = asyncio.Queue()
        handler = NodeLifecycleHandler(queue)

        async def run_graph():
            try:
                config = {
                    "configurable": {"thread_id": thread_id},
                    "callbacks": [handler],
                }
                if req.resume:
                    # 断点续跑：不注入新输入，从上次中断的检查点继续
                    stream = graph.astream(None, config=config, stream_mode="updates")
                else:
                    initial_state = {
                        "messages": [HumanMessage(content=req.message or "执行全链路智能上新")],
                        "user_intent": intent,
                        "disabled_stages": disabled,
                        "target_platform": req.target_platform,
                        "target_market": req.target_market,
                        "product_image_url": req.product_image_url,
                        "imported_images": req.imported_images or [],
                        "trace": [],
                        # ── 注入 1688 真实数据 ──
                        "product_title": req.product_title or "",
                        "supply_price_cny": req.supply_price_cny,
                        "sku_attributes": req.sku_attributes or {},
                        "source_url": req.source_url or "",
                    }
                    stream = graph.astream(initial_state, config=config, stream_mode="updates")

                async for event in stream:
                    for node_name, node_update in event.items():
                        if node_name not in PIPELINE_NODES:
                            continue
                        queue.put_nowait({
                            "type": "node_update",
                            "node": node_name,
                            "update": node_update,
                            "ts": time.time(),
                        })
                queue.put_nowait({"type": "done"})
            except Exception as e:
                queue.put_nowait({"type": "error", "error": str(e)})

        task = asyncio.create_task(run_graph())

        def _progress_payload(running: Optional[str]) -> Dict[str, Any]:
            total = len(planned_ids)
            done_ratio = len(completed) / total if total else 1
            return {
                "progress": round(done_ratio * 100),
                "eta_seconds": estimate_remaining_eta(intent, completed, running, disabled),
                "completed_nodes": list(completed),
                "running_node": running,
            }

        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=5.0)
                except asyncio.TimeoutError:
                    # 每 5 秒发送 SSE 心跳注释，防止浏览器/代理/客户端连接超时断开
                    yield ": ping\n\n"
                    continue

                kind = item["type"]

                if kind == "node_start":
                    node_started_at[item["node"]] = item["ts"]
                    yield _sse("node_start", {
                        "node": item["node"],
                        "status": "running",
                        **_progress_payload(item["node"]),
                    })

                elif kind == "node_update":
                    node_name = item["node"]
                    node_update = item["update"]
                    if node_name not in completed:
                        completed.append(node_name)

                    trace = node_update.get("trace", [])
                    last_trace = trace[-1] if trace else None
                    summary = last_trace.get("summary") if last_trace else f"节点 {node_name} 执行完毕"
                    started = node_started_at.get(node_name)
                    duration = round(item["ts"] - started, 1) if started else None

                    yield _sse("node_update", {
                        "event_type": "node_update",
                        "node": node_name,
                        "status": "completed",
                        "summary": summary,
                        "duration_seconds": duration,
                        "data": _json_safe(node_update),
                        **_progress_payload(None),
                    })

                elif kind == "done":
                    break

                elif kind == "error":
                    yield _sse("error", {
                        "event_type": "error",
                        "error": item.get("error", "未知错误"),
                        "thread_id": thread_id,
                        "resumable": True,
                        **_progress_payload(None),
                    })
                    return

            # 读取最终状态并落库
            final_snapshot = graph.get_state({"configurable": {"thread_id": thread_id}})
            final_values = final_snapshot.values if final_snapshot else {}

            result = {
                "product_attributes": final_values.get("product_attributes"),
                "market_insights": final_values.get("market_insights"),
                "trend_benchmark": final_values.get("trend_benchmark"),
                "listing_content": final_values.get("listing_content"),
                "studio_assets": final_values.get("studio_assets"),
                "video_package": final_values.get("video_package"),
                "localized_images": final_values.get("localized_images"),
                "platform_package": final_values.get("platform_package"),
                # V2 新增：领域模型输出
                "opportunity_score": final_values.get("opportunity_score"),
                "asset_inventory": final_values.get("asset_inventory"),
                "asset_gap": final_values.get("asset_gap"),
                "listing_health": final_values.get("listing_health"),
                "publish_package": final_values.get("publish_package"),
                "final_reply": final_values.get("messages", [])[-1].content if final_values.get("messages") else "",
                "trace": final_values.get("trace", [])
            }

            try:
                TaskStore.get_instance().save_task(
                    thread_id, result,
                    platform=req.target_platform or "",
                    market=req.target_market or "",
                    intent=intent,
                    message=req.message,
                )
                # Listing 版本存档（供同商品多次上新的版本对比）
                TaskStore.get_instance().save_version(
                    thread_id,
                    result.get("listing_content") or {},
                    category=(result.get("product_attributes") or {}).get("category", ""),
                    platform=req.target_platform or "",
                    market=req.target_market or "",
                )
            except Exception:
                # 持久化失败不影响主流程
                pass

            yield _sse("complete", {
                "event_type": "finished",
                "thread_id": thread_id,
                "progress": 100,
                "result": result,
            })
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
