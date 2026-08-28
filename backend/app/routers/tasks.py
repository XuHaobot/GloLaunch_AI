"""任务历史：查询历史上新任务、单个任务详情与 Listing 版本对比（数据来自 SQLite 持久化）"""
from fastapi import APIRouter, HTTPException

from app.services.task_store import TaskStore

router = APIRouter(prefix="/api/tasks", tags=["任务历史"])

@router.get("")
async def list_tasks(limit: int = 20):
    """历史任务列表（按时间倒序）"""
    tasks = TaskStore.get_instance().list_tasks(limit=min(limit, 100))
    return {"status": "success", "tasks": tasks}

# ---------- Listing 版本对比（路由需声明在 /{thread_id} 之前避免被通配拦截） ----------
@router.get("/versions")
async def list_versions(limit: int = 30):
    """Listing 版本列表（每次上新自动存档）"""
    versions = TaskStore.get_instance().list_versions(limit=min(limit, 100))
    return {"status": "success", "versions": versions}

@router.get("/versions/compare")
async def compare_versions(a: int, b: int):
    """两个 Listing 版本的对比（含字段级变化摘要）"""
    store = TaskStore.get_instance()
    va, vb = store.get_version(a), store.get_version(b)
    if not va or not vb:
        raise HTTPException(status_code=404, detail="版本不存在")

    la, lb = va.get("listing", {}), vb.get("listing", {})
    bullets_a, bullets_b = la.get("bullet_points", []), lb.get("bullet_points", [])
    diff_summary = {
        "title_changed": la.get("title") != lb.get("title"),
        "title_length_delta": len(lb.get("title", "")) - len(la.get("title", "")),
        "bullets_added": max(0, len(bullets_b) - len(bullets_a)),
        "bullets_removed": max(0, len(bullets_a) - len(bullets_b)),
        "bullets_changed": sum(1 for x, y in zip(bullets_a, bullets_b) if x != y),
        "search_terms_changed": la.get("search_terms") != lb.get("search_terms"),
    }
    return {"status": "success", "version_a": va, "version_b": vb, "diff_summary": diff_summary}

@router.get("/{thread_id}")
async def get_task(thread_id: str):
    """单个任务详情（含完整结果体，可用于前端回看）"""
    task = TaskStore.get_instance().get_task(thread_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"status": "success", "task": task}
