"""SQLite storage helpers for the local dashboard."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

DB_PATH = Path("paper_radio.db")


def utc_now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                progress INTEGER NOT NULL DEFAULT 0,
                params_json TEXT NOT NULL DEFAULT '{}',
                result_json TEXT NOT NULL DEFAULT '{}',
                error TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS job_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                level TEXT NOT NULL,
                message TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS deep_analysis (
                arxiv_id TEXT NOT NULL,
                date TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                analysis_markdown TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                error TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (arxiv_id, date)
            );

            CREATE TABLE IF NOT EXISTS favorites (
                arxiv_id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '',
                source_date TEXT NOT NULL DEFAULT '',
                primary_url TEXT NOT NULL DEFAULT '',
                topic_category TEXT NOT NULL DEFAULT '',
                tags_json TEXT NOT NULL DEFAULT '[]',
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS paper_state (
                arxiv_id TEXT NOT NULL,
                date TEXT NOT NULL DEFAULT '',
                is_read INTEGER NOT NULL DEFAULT 0,
                archived INTEGER NOT NULL DEFAULT 0,
                upvoted INTEGER NOT NULL DEFAULT 0,
                downvoted INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (arxiv_id, date)
            );

            CREATE TABLE IF NOT EXISTS schedules (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT 'Daily mining',
                enabled INTEGER NOT NULL DEFAULT 0,
                days INTEGER NOT NULL DEFAULT 1,
                categories_json TEXT NOT NULL DEFAULT '[]',
                run_time TEXT NOT NULL DEFAULT '09:00',
                last_run_at TEXT NOT NULL DEFAULT '',
                next_run_at TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS config_overrides (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS config_change_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL,
                old_value_json TEXT NOT NULL DEFAULT 'null',
                new_value_json TEXT NOT NULL DEFAULT 'null',
                source TEXT NOT NULL DEFAULT 'manual',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS paper_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                arxiv_id TEXT NOT NULL,
                date TEXT NOT NULL DEFAULT '',
                feedback_type TEXT NOT NULL DEFAULT 'downvote',
                reason TEXT NOT NULL,
                paper_json TEXT NOT NULL DEFAULT '{}',
                suggestion_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        _ensure_column(conn, "paper_state", "upvoted", "INTEGER NOT NULL DEFAULT 0")


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _ensure_paper_state_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS paper_state (
            arxiv_id TEXT NOT NULL,
            date TEXT NOT NULL DEFAULT '',
            is_read INTEGER NOT NULL DEFAULT 0,
            archived INTEGER NOT NULL DEFAULT 0,
            upvoted INTEGER NOT NULL DEFAULT 0,
            downvoted INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (arxiv_id, date)
        )
        """
    )
    _ensure_column(conn, "paper_state", "upvoted", "INTEGER NOT NULL DEFAULT 0")


def _row_to_dict(row: sqlite3.Row | None) -> Optional[Dict[str, Any]]:
    return dict(row) if row is not None else None


def create_job(job_id: str, job_type: str, params: Dict[str, Any]) -> None:
    now = utc_now()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs (id, type, status, created_at, progress, params_json)
            VALUES (?, ?, 'queued', ?, 0, ?)
            """,
            (job_id, job_type, now, json.dumps(params, ensure_ascii=False)),
        )


def update_job(
    job_id: str,
    *,
    status: Optional[str] = None,
    progress: Optional[int] = None,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    started: bool = False,
    finished: bool = False,
) -> None:
    fields: List[str] = []
    values: List[Any] = []
    if status is not None:
        fields.append("status = ?")
        values.append(status)
    if progress is not None:
        fields.append("progress = ?")
        values.append(max(0, min(100, int(progress))))
    if result is not None:
        fields.append("result_json = ?")
        values.append(json.dumps(result, ensure_ascii=False))
    if error is not None:
        fields.append("error = ?")
        values.append(error)
    if started:
        fields.append("started_at = ?")
        values.append(utc_now())
    if finished:
        fields.append("finished_at = ?")
        values.append(utc_now())
    if not fields:
        return
    values.append(job_id)
    with connect() as conn:
        conn.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE id = ?", values)


def add_job_log(job_id: str, message: str, level: str = "info") -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO job_logs (job_id, created_at, level, message) VALUES (?, ?, ?, ?)",
            (job_id, utc_now(), level, message),
        )


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    item = _row_to_dict(row)
    if not item:
        return None
    item["params"] = json.loads(item.pop("params_json") or "{}")
    item["result"] = json.loads(item.pop("result_json") or "{}")
    return item


def list_jobs(limit: int = 20) -> List[Dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [get_job(row["id"]) for row in rows if row["id"]]


def list_tasks(limit: int = 50) -> List[Dict[str, Any]]:
    return list_jobs(limit=limit)


def list_job_logs(job_id: str) -> List[Dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM job_logs WHERE job_id = ? ORDER BY id ASC", (job_id,)
        ).fetchall()
    return [dict(row) for row in rows]


def has_running_job(job_type: str) -> bool:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM jobs
            WHERE type = ? AND status IN ('queued', 'running', 'cancel_requested')
            LIMIT 1
            """,
            (job_type,),
        ).fetchone()
    return row is not None


def reset_active_jobs(job_type: str = "mining") -> int:
    """Mark stuck queued/running jobs as canceled without touching favorites/cache."""
    now = utc_now()
    with connect() as conn:
        cur = conn.execute(
            """
            UPDATE jobs
            SET status = 'canceled',
                finished_at = COALESCE(finished_at, ?),
                error = CASE WHEN error = '' THEN '手动重置卡住的任务' ELSE error END
            WHERE type = ? AND status IN ('queued', 'running', 'cancel_requested')
            """,
            (now, job_type),
        )
    return cur.rowcount


def upsert_deep_analysis(
    arxiv_id: str,
    date: str,
    *,
    status: str,
    analysis_markdown: str = "",
    error: str = "",
) -> None:
    now = utc_now()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO deep_analysis
                (arxiv_id, date, status, analysis_markdown, created_at, updated_at, error)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(arxiv_id, date) DO UPDATE SET
                status = excluded.status,
                analysis_markdown = excluded.analysis_markdown,
                updated_at = excluded.updated_at,
                error = excluded.error
            """,
            (arxiv_id, date or "", status, analysis_markdown, now, now, error),
        )


def get_deep_analysis(arxiv_id: str, date: str = "") -> Optional[Dict[str, Any]]:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM deep_analysis WHERE arxiv_id = ? AND date = ?",
            (arxiv_id, date or ""),
        ).fetchone()
    return _row_to_dict(row)


def list_deep_analysis(date: str = "") -> List[Dict[str, Any]]:
    query = "SELECT * FROM deep_analysis"
    params: Iterable[Any] = ()
    if date:
        query += " WHERE date = ?"
        params = (date,)
    query += " ORDER BY updated_at DESC"
    with connect() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def upsert_favorite(
    arxiv_id: str,
    *,
    title: str = "",
    source_date: str = "",
    primary_url: str = "",
    topic_category: str = "",
    tags: Optional[List[str]] = None,
    note: str = "",
) -> Dict[str, Any]:
    now = utc_now()
    tags_json = json.dumps(tags or [], ensure_ascii=False)
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO favorites
                (arxiv_id, title, source_date, primary_url, topic_category, tags_json, note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(arxiv_id) DO UPDATE SET
                title = COALESCE(NULLIF(excluded.title, ''), favorites.title),
                source_date = COALESCE(NULLIF(excluded.source_date, ''), favorites.source_date),
                primary_url = COALESCE(NULLIF(excluded.primary_url, ''), favorites.primary_url),
                topic_category = COALESCE(NULLIF(excluded.topic_category, ''), favorites.topic_category),
                tags_json = excluded.tags_json,
                note = excluded.note,
                updated_at = excluded.updated_at
            """,
            (
                arxiv_id,
                title,
                source_date,
                primary_url,
                topic_category,
                tags_json,
                note,
                now,
                now,
            ),
        )
    return get_favorite(arxiv_id) or {}


def get_favorite(arxiv_id: str) -> Optional[Dict[str, Any]]:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM favorites WHERE arxiv_id = ?", (arxiv_id,)
        ).fetchone()
    item = _row_to_dict(row)
    if item:
        item["tags"] = json.loads(item.pop("tags_json") or "[]")
    return item


def list_favorites() -> List[Dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM favorites ORDER BY updated_at DESC"
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["tags"] = json.loads(item.pop("tags_json") or "[]")
        result.append(item)
    return result


def delete_favorite(arxiv_id: str) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM favorites WHERE arxiv_id = ?", (arxiv_id,))
    return cur.rowcount > 0


def get_paper_state(arxiv_id: str, date: str = "") -> Dict[str, Any]:
    with connect() as conn:
        _ensure_paper_state_table(conn)
        row = conn.execute(
            "SELECT * FROM paper_state WHERE arxiv_id = ? AND date = ?",
            (arxiv_id, date or ""),
        ).fetchone()
    item = _row_to_dict(row) or {
        "arxiv_id": arxiv_id,
        "date": date or "",
        "is_read": 0,
        "archived": 0,
        "upvoted": 0,
        "downvoted": 0,
        "updated_at": "",
    }
    item["read"] = bool(item.get("is_read"))
    item["archived"] = bool(item.get("archived"))
    item["upvoted"] = bool(item.get("upvoted"))
    item["downvoted"] = bool(item.get("downvoted"))
    return item


def upsert_paper_state(
    arxiv_id: str,
    date: str = "",
    *,
    read: Optional[bool] = None,
    archived: Optional[bool] = None,
    upvoted: Optional[bool] = None,
    downvoted: Optional[bool] = None,
) -> Dict[str, Any]:
    current = get_paper_state(arxiv_id, date)
    is_read = int(current["read"] if read is None else read)
    is_archived = int(current["archived"] if archived is None else archived)
    is_upvoted = int(current["upvoted"] if upvoted is None else upvoted)
    is_downvoted = int(current["downvoted"] if downvoted is None else downvoted)
    now = utc_now()
    with connect() as conn:
        _ensure_paper_state_table(conn)
        conn.execute(
            """
            INSERT INTO paper_state (arxiv_id, date, is_read, archived, upvoted, downvoted, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(arxiv_id, date) DO UPDATE SET
                is_read = excluded.is_read,
                archived = excluded.archived,
                upvoted = excluded.upvoted,
                downvoted = excluded.downvoted,
                updated_at = excluded.updated_at
            """,
            (arxiv_id, date or "", is_read, is_archived, is_upvoted, is_downvoted, now),
        )
    return get_paper_state(arxiv_id, date)


def list_paper_states(date: str = "") -> List[Dict[str, Any]]:
    query = "SELECT * FROM paper_state"
    params: Iterable[Any] = ()
    if date:
        query += " WHERE date = ?"
        params = (date,)
    query += " ORDER BY updated_at DESC"
    with connect() as conn:
        _ensure_paper_state_table(conn)
        rows = conn.execute(query, tuple(params)).fetchall()
    return [get_paper_state(row["arxiv_id"], row["date"]) for row in rows]


def list_schedules() -> List[Dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM schedules ORDER BY created_at ASC").fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["enabled"] = bool(item["enabled"])
        item["categories"] = json.loads(item.pop("categories_json") or "[]")
        result.append(item)
    return result


def upsert_schedule(
    schedule_id: str,
    *,
    name: str = "Daily mining",
    enabled: bool = False,
    days: int = 1,
    categories: Optional[List[str]] = None,
    run_time: str = "09:00",
    last_run_at: str = "",
    next_run_at: str = "",
) -> Dict[str, Any]:
    now = utc_now()
    categories_json = json.dumps(categories or [], ensure_ascii=False)
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO schedules
                (id, name, enabled, days, categories_json, run_time, last_run_at, next_run_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                enabled = excluded.enabled,
                days = excluded.days,
                categories_json = excluded.categories_json,
                run_time = excluded.run_time,
                last_run_at = CASE WHEN excluded.last_run_at != '' THEN excluded.last_run_at ELSE schedules.last_run_at END,
                next_run_at = excluded.next_run_at,
                updated_at = excluded.updated_at
            """,
            (
                schedule_id,
                name,
                int(enabled),
                int(days),
                categories_json,
                run_time,
                last_run_at,
                next_run_at,
                now,
                now,
            ),
        )
    return get_schedule(schedule_id) or {}


def get_schedule(schedule_id: str) -> Optional[Dict[str, Any]]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
    if not row:
        return None
    item = dict(row)
    item["enabled"] = bool(item["enabled"])
    item["categories"] = json.loads(item.pop("categories_json") or "[]")
    return item


def set_schedule_run_times(schedule_id: str, *, last_run_at: str = "", next_run_at: str = "") -> None:
    fields: List[str] = []
    values: List[Any] = []
    if last_run_at:
        fields.append("last_run_at = ?")
        values.append(last_run_at)
    if next_run_at:
        fields.append("next_run_at = ?")
        values.append(next_run_at)
    if not fields:
        return
    fields.append("updated_at = ?")
    values.append(utc_now())
    values.append(schedule_id)
    with connect() as conn:
        conn.execute(f"UPDATE schedules SET {', '.join(fields)} WHERE id = ?", values)


def get_config_overrides() -> Dict[str, Any]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM config_overrides").fetchall()
    return {row["key"]: json.loads(row["value_json"]) for row in rows}


def set_config_override(key: str, value: Any, *, source: str = "manual") -> Dict[str, Any]:
    old = get_config_overrides().get(key)
    now = utc_now()
    value_json = json.dumps(value, ensure_ascii=False)
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO config_overrides (key, value_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value_json = excluded.value_json,
                updated_at = excluded.updated_at
            """,
            (key, value_json, now),
        )
        conn.execute(
            """
            INSERT INTO config_change_log (key, old_value_json, new_value_json, source, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                key,
                json.dumps(old, ensure_ascii=False),
                value_json,
                source,
                now,
            ),
        )
    return {"key": key, "value": value, "updated_at": now}


def reset_config_override(key: str, *, source: str = "manual") -> bool:
    old = get_config_overrides().get(key)
    now = utc_now()
    with connect() as conn:
        cur = conn.execute("DELETE FROM config_overrides WHERE key = ?", (key,))
        if cur.rowcount:
            conn.execute(
                """
                INSERT INTO config_change_log (key, old_value_json, new_value_json, source, created_at)
                VALUES (?, ?, 'null', ?, ?)
                """,
                (key, json.dumps(old, ensure_ascii=False), source, now),
            )
    return cur.rowcount > 0


def create_feedback(
    arxiv_id: str,
    *,
    date: str = "",
    reason: str,
    paper: Optional[Dict[str, Any]] = None,
    suggestion: Optional[Dict[str, Any]] = None,
    feedback_type: str = "downvote",
) -> Dict[str, Any]:
    now = utc_now()
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO paper_feedback
                (arxiv_id, date, feedback_type, reason, paper_json, suggestion_json, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                arxiv_id,
                date or "",
                feedback_type,
                reason,
                json.dumps(paper or {}, ensure_ascii=False),
                json.dumps(suggestion or {}, ensure_ascii=False),
                now,
                now,
            ),
        )
        feedback_id = cur.lastrowid
    return get_feedback(feedback_id) or {}


def get_feedback(feedback_id: int) -> Optional[Dict[str, Any]]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM paper_feedback WHERE id = ?", (feedback_id,)).fetchone()
    item = _row_to_dict(row)
    if item:
        item["paper"] = json.loads(item.pop("paper_json") or "{}")
        item["suggestion"] = json.loads(item.pop("suggestion_json") or "{}")
    return item


def list_feedback(limit: int = 50) -> List[Dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id FROM paper_feedback ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [get_feedback(row["id"]) for row in rows if row["id"]]


def update_feedback_status(feedback_id: int, status: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE paper_feedback SET status = ?, updated_at = ? WHERE id = ?",
            (status, utc_now(), feedback_id),
        )
