"""SQLite 任务持久化：记录每次上新任务的执行结果，支持历史任务查询与回看。"""
import json
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional

from app.config import get_settings

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    thread_id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    platform TEXT,
    market TEXT,
    intent TEXT,
    category TEXT,
    message TEXT,
    status TEXT DEFAULT 'completed',
    result_json TEXT
)
"""

_CREATE_VERSIONS_SQL = """
CREATE TABLE IF NOT EXISTS listing_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    category TEXT,
    platform TEXT,
    market TEXT,
    title TEXT,
    listing_json TEXT NOT NULL
)
"""

_CREATE_PUBLISHES_SQL = """
CREATE TABLE IF NOT EXISTS publish_records (
    publish_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    platform TEXT,
    market TEXT,
    mode TEXT,
    status TEXT,
    report_json TEXT
)
"""

class TaskStore:
    _instance = None

    def __init__(self):
        settings = get_settings()
        db_path = settings.sqlite_path
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self.db_path = db_path
        with self._connect() as conn:
            conn.execute(_CREATE_TABLE_SQL)
            conn.execute(_CREATE_VERSIONS_SQL)
            conn.execute(_CREATE_PUBLISHES_SQL)

    @classmethod
    def get_instance(cls) -> "TaskStore":
        if cls._instance is None:
            cls._instance = TaskStore()
        return cls._instance

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def save_task(self, thread_id: str, result: Dict[str, Any],
                  platform: str = "", market: str = "", intent: str = "full_launch",
                  message: str = "") -> None:
        """保存（或覆盖）一次任务执行结果"""
        attrs = (result or {}).get("product_attributes") or {}
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO tasks (thread_id, created_at, platform, market, intent, category, message, status, result_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'completed', ?)
                   ON CONFLICT(thread_id) DO UPDATE SET
                     created_at = excluded.created_at,
                     status = excluded.status,
                     result_json = excluded.result_json,
                     category = excluded.category""",
                (
                    thread_id, time.time(), platform, market, intent,
                    attrs.get("category", ""), message,
                    json.dumps(result or {}, ensure_ascii=False),
                ),
            )

    def list_tasks(self, limit: int = 20) -> List[Dict[str, Any]]:
        """任务历史列表（不含完整结果体，降低传输量）"""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT thread_id, created_at, platform, market, intent, category, message, status
                   FROM tasks ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_task(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """读取单个任务详情（含完整结果体）"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE thread_id = ?", (thread_id,)
            ).fetchone()
        if not row:
            return None
        task = dict(row)
        try:
            task["result"] = json.loads(task.pop("result_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            task["result"] = {}
        return task

    # ---------- Listing 版本存档（同一商品多次上新的版本对比） ----------
    def save_version(self, thread_id: str, listing: Dict[str, Any],
                     category: str = "", platform: str = "", market: str = "") -> None:
        """每次上新完成后存档一份 Listing 版本（仅当含有效标题时）"""
        if not listing or not listing.get("title"):
            return
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO listing_versions (thread_id, created_at, category, platform, market, title, listing_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    thread_id, time.time(), category, platform, market,
                    listing.get("title", ""),
                    json.dumps(listing, ensure_ascii=False),
                ),
            )

    def list_versions(self, limit: int = 30) -> List[Dict[str, Any]]:
        """版本列表（不含完整 Listing 体，供选择对比）"""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT id, thread_id, created_at, category, platform, market, title
                   FROM listing_versions ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_version(self, version_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM listing_versions WHERE id = ?", (version_id,)
            ).fetchone()
        if not row:
            return None
        version = dict(row)
        try:
            version["listing"] = json.loads(version.pop("listing_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            version["listing"] = {}
        return version

    # ---------- 平台发布记录 ----------
    def save_publish(self, publish_id: str, thread_id: str, platform: str,
                     market: str, mode: str, status: str, report: Dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO publish_records (publish_id, thread_id, created_at, platform, market, mode, status, report_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(publish_id) DO UPDATE SET status = excluded.status, report_json = excluded.report_json""",
                (publish_id, thread_id, time.time(), platform, market, mode, status,
                 json.dumps(report or {}, ensure_ascii=False)),
            )
