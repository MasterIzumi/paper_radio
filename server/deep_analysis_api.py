"""On-demand deep analysis APIs."""
from __future__ import annotations

import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from pipeline.deep_analysis import find_paper_payload, run_deep_analysis_for_paper
from pipeline.deep_analysis_reports import report_path_for, write_deep_analysis_report
from storage import db

router = APIRouter(prefix="/api/papers", tags=["deep-analysis"])
collection_router = APIRouter(prefix="/api/deep-analysis", tags=["deep-analysis"])


def _metadata_for(arxiv_id: str, date: str = "") -> dict:
    payload = find_paper_payload(arxiv_id, date=date) or {}
    return {
        "title": payload.get("title") or arxiv_id,
        "authors": payload.get("authors") or [],
        "authors_display": payload.get("authors_display") or "",
        "topic_category": payload.get("topic_category") or "未分类",
        "total_score": payload.get("total_score") or "",
        "relevance_score": payload.get("relevance_score") or "",
        "novelty_score": payload.get("novelty_score") or "",
        "one_line_summary": payload.get("one_line_summary") or "",
        "primary_url": payload.get("primary_url") or f"https://arxiv.org/abs/{arxiv_id}",
        "announced_day": payload.get("announced_day") or date,
    }


def _with_metadata(item: dict) -> dict:
    arxiv_id = item.get("arxiv_id", "")
    date = item.get("date", "")
    metadata = _metadata_for(arxiv_id, date=date)
    report_path = report_path_for(arxiv_id)
    if (
        item.get("status") == "succeeded"
        and item.get("analysis_markdown")
        and not report_path.exists()
    ):
        write_deep_analysis_report(
            {
                "arxiv_id": arxiv_id,
                "date": date or metadata.get("announced_day", ""),
                "title": metadata.get("title") or arxiv_id,
                "model": "",
                "generated_at": item.get("updated_at", ""),
                "analysis_markdown": item.get("analysis_markdown", ""),
            }
        )
    return {
        **item,
        **metadata,
        "report_path": str(report_path),
        "report_exists": report_path.exists(),
    }


def _run_deep_analysis(arxiv_id: str, date: str) -> None:
    try:
        result = run_deep_analysis_for_paper(arxiv_id, date=date)
        db.upsert_deep_analysis(
            arxiv_id,
            date,
            status="succeeded",
            analysis_markdown=result["analysis_markdown"],
        )
    except Exception as exc:
        db.upsert_deep_analysis(arxiv_id, date, status="failed", error=str(exc))


@router.post("/{arxiv_id}/deep-analysis")
def create_deep_analysis(arxiv_id: str, date: str = Query(default="")):
    cached = db.get_deep_analysis(arxiv_id, date)
    if cached and cached["status"] == "succeeded":
        return _with_metadata(cached)
    if cached and cached["status"] == "running":
        return _with_metadata(cached)

    db.upsert_deep_analysis(arxiv_id, date, status="running")
    thread = threading.Thread(target=_run_deep_analysis, args=(arxiv_id, date), daemon=True)
    thread.start()
    return _with_metadata(db.get_deep_analysis(arxiv_id, date) or {})


@router.get("/{arxiv_id}/deep-analysis")
def get_deep_analysis(arxiv_id: str, date: str = Query(default="")):
    item = db.get_deep_analysis(arxiv_id, date)
    if not item:
        raise HTTPException(status_code=404, detail="deep analysis not found")
    return _with_metadata(item)


@collection_router.get("")
def list_deep_analysis(date: str = Query(default="")):
    items = [_with_metadata(item) for item in db.list_deep_analysis(date=date)]
    for item in items:
        item.pop("analysis_markdown", None)
    return {"items": items}


@collection_router.get("/{arxiv_id}/report")
def get_deep_analysis_report(arxiv_id: str, date: str = Query(default="")):
    item = db.get_deep_analysis(arxiv_id, date)
    if not item:
        raise HTTPException(status_code=404, detail="deep analysis not found")

    payload = _with_metadata(item)
    path = Path(payload["report_path"])
    if path.exists():
        payload["report_markdown"] = path.read_text(encoding="utf-8")
    else:
        payload["report_markdown"] = item.get("analysis_markdown", "")
    return payload
