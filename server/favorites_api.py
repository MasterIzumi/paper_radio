"""Favorite paper APIs."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from storage import db

router = APIRouter(prefix="/api/favorites", tags=["favorites"])


class FavoritePayload(BaseModel):
    title: str = ""
    source_date: str = ""
    primary_url: str = ""
    topic_category: str = ""
    tags: List[str] = Field(default_factory=list)
    note: str = ""


@router.get("")
def list_favorites():
    return {"favorites": db.list_favorites()}


@router.post("/{arxiv_id}")
def add_favorite(arxiv_id: str, payload: FavoritePayload):
    return db.upsert_favorite(
        arxiv_id,
        title=payload.title,
        source_date=payload.source_date,
        primary_url=payload.primary_url,
        topic_category=payload.topic_category,
        tags=payload.tags,
        note=payload.note,
    )


@router.patch("/{arxiv_id}")
def update_favorite(arxiv_id: str, payload: FavoritePayload):
    if not db.get_favorite(arxiv_id):
        raise HTTPException(status_code=404, detail="favorite not found")
    return db.upsert_favorite(
        arxiv_id,
        title=payload.title,
        source_date=payload.source_date,
        primary_url=payload.primary_url,
        topic_category=payload.topic_category,
        tags=payload.tags,
        note=payload.note,
    )


@router.delete("/{arxiv_id}")
def delete_favorite(arxiv_id: str):
    if not db.delete_favorite(arxiv_id):
        raise HTTPException(status_code=404, detail="favorite not found")
    return {"ok": True}
