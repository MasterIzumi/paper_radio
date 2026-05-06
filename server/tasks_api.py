"""Global task list APIs."""
from __future__ import annotations

from fastapi import APIRouter

from pipeline.deep_analysis import find_paper_payload
from storage import db

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _synthetic_deep_analysis_tasks(limit: int = 50):
    jobs = db.list_tasks(limit=limit)
    existing = {
        (
            item.get("params", {}).get("arxiv_id", ""),
            item.get("params", {}).get("date", ""),
        )
        for item in jobs
        if item.get("type") == "AI解读"
    }

    synthetic = []
    for item in db.list_deep_analysis()[:limit]:
        key = (item.get("arxiv_id", ""), item.get("date", ""))
        if key in existing:
            continue
        payload = find_paper_payload(item.get("arxiv_id", ""), date=item.get("date", "")) or {}
        status = item.get("status", "")
        synthetic.append(
            {
                "id": f"deep-analysis:{item.get('arxiv_id', '')}:{item.get('date', '')}",
                "type": "AI解读",
                "status": status,
                "created_at": item.get("created_at", ""),
                "started_at": item.get("created_at", ""),
                "finished_at": item.get("updated_at", "") if status in {"succeeded", "failed"} else "",
                "progress": 100 if status in {"succeeded", "failed"} else 50,
                "params": {
                    "arxiv_id": item.get("arxiv_id", ""),
                    "date": item.get("date", ""),
                    "title": payload.get("title", item.get("arxiv_id", "")),
                    "source": "manual",
                },
                "result": {},
                "error": item.get("error", "") or "",
            }
        )
    return synthetic


@router.get("")
def list_tasks():
    jobs = db.list_tasks(limit=50)
    tasks = sorted(
        jobs + _synthetic_deep_analysis_tasks(limit=50),
        key=lambda item: item.get("created_at", ""),
        reverse=True,
    )
    return {"tasks": tasks[:50]}
