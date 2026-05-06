"""On-demand deep analysis APIs."""
from __future__ import annotations

import threading
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from pipeline.deep_analysis import find_paper_payload, run_deep_analysis_for_paper
from pipeline.deep_analysis_reports import report_dir_for, report_path_for, write_deep_analysis_report
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


def _run_deep_analysis_job(job_id: str, arxiv_id: str, date: str) -> None:
    try:
        db.update_job(job_id, status="running", progress=5, started=True)
        db.add_job_log(job_id, f"开始生成 {arxiv_id} 的 AI解读")
        result = run_deep_analysis_for_paper(arxiv_id, date=date)
        db.upsert_deep_analysis(
            arxiv_id,
            date,
            status="succeeded",
            analysis_markdown=result["analysis_markdown"],
        )
        db.update_job(
            job_id,
            status="succeeded",
            progress=100,
            result={
                "arxiv_id": arxiv_id,
                "date": date,
                "report_path": result.get("report_path", ""),
            },
            finished=True,
        )
        db.add_job_log(job_id, "AI解读完成")
    except Exception as exc:
        db.upsert_deep_analysis(arxiv_id, date, status="failed", error=str(exc))
        db.update_job(
            job_id,
            status="failed",
            error=str(exc),
            finished=True,
        )
        db.add_job_log(job_id, f"AI解读失败：{exc}", level="error")


def _delete_report_artifact(arxiv_id: str) -> None:
    path = report_path_for(arxiv_id)
    if path.exists():
        path.unlink()
    report_dir = report_dir_for(arxiv_id)
    if report_dir.exists() and not any(report_dir.iterdir()):
        report_dir.rmdir()


@router.post("/{arxiv_id}/deep-analysis")
def create_deep_analysis(arxiv_id: str, date: str = Query(default="")):
    cached = db.get_deep_analysis(arxiv_id, date)
    if cached and cached["status"] == "succeeded":
        return _with_metadata(cached)
    if cached and cached["status"] == "running":
        return _with_metadata(cached)

    db.upsert_deep_analysis(arxiv_id, date, status="running")
    metadata = _metadata_for(arxiv_id, date=date)
    job_id = uuid.uuid4().hex
    db.create_job(
        job_id,
        "AI解读",
        {
            "arxiv_id": arxiv_id,
            "date": date,
            "title": metadata.get("title", arxiv_id),
            "source": "manual",
        },
    )
    db.add_job_log(job_id, "任务排队中")
    thread = threading.Thread(target=_run_deep_analysis_job, args=(job_id, arxiv_id, date), daemon=True)
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


@collection_router.delete("/{arxiv_id}")
def delete_deep_analysis(arxiv_id: str, date: str = Query(default="")):
    item = db.get_deep_analysis(arxiv_id, date)
    if not item:
        raise HTTPException(status_code=404, detail="deep analysis not found")
    deleted = db.delete_deep_analysis(arxiv_id, date)
    if deleted:
        _delete_report_artifact(arxiv_id)
    return {"ok": deleted, "arxiv_id": arxiv_id, "date": date or ""}
