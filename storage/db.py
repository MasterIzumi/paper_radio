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
            """
        )


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
