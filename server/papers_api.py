"""Paper detail and state APIs."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from pipeline.deep_analysis import find_paper_payload
from storage import db

router = APIRouter(prefix="/api/papers", tags=["papers"])


class PaperStatePayload(BaseModel):
    date: str = ""
    read: Optional[bool] = None
    archived: Optional[bool] = None
    upvoted: Optional[bool] = None
    downvoted: Optional[bool] = None


def _paper_with_state(arxiv_id: str, date: str = "") -> Dict[str, Any]:
    payload = find_paper_payload(arxiv_id, date=date)
    if not payload:
        raise HTTPException(status_code=404, detail="paper not found")
    resolved_date = date or payload.get("announced_day") or payload.get("date") or ""
    state = db.get_paper_state(arxiv_id, resolved_date)
    insight = db.get_deep_analysis(arxiv_id, resolved_date) or db.get_deep_analysis(arxiv_id, "")
    favorite = db.get_favorite(arxiv_id)
    return {
        **payload,
        "state": state,
        "ai_insight_status": insight.get("status") if insight else "",
        "favorite": favorite,
    }


@router.get("/state/list")
def list_paper_states(date: str = Query(default="")):
    return {"states": db.list_paper_states(date=date)}


@router.patch("/{arxiv_id}/state")
def update_paper_state(arxiv_id: str, payload: PaperStatePayload):
    return db.upsert_paper_state(
        arxiv_id,
        payload.date,
        read=payload.read,
        archived=payload.archived,
        upvoted=payload.upvoted,
        downvoted=payload.downvoted,
    )


@router.get("/{arxiv_id}")
def get_paper(arxiv_id: str, date: str = Query(default="")):
    return _paper_with_state(arxiv_id, date=date)
