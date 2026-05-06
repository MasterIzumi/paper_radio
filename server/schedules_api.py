"""Schedule management APIs."""
from __future__ import annotations

from typing import List, Union

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import config
from recent_report import parse_categories_arg
from server.scheduler import next_run_at
from storage import db

router = APIRouter(prefix="/api/schedules", tags=["schedules"])


class SchedulePayload(BaseModel):
    enabled: bool = False
    days: int = Field(default=1, ge=1, le=30)
    categories: Union[List[str], str] = Field(default_factory=lambda: list(config.FETCH_CATEGORIES))
    run_time: str = "09:00"


@router.get("")
def list_schedules():
    return {"schedules": db.list_schedules()}


@router.post("")
def save_schedule(payload: SchedulePayload):
    raw_categories = ",".join(payload.categories) if isinstance(payload.categories, list) else payload.categories
    categories = parse_categories_arg(raw_categories, config.FETCH_CATEGORIES)
    return db.upsert_schedule(
        "daily-mining",
        enabled=payload.enabled,
        days=payload.days,
        categories=categories,
        run_time=payload.run_time,
        next_run_at=next_run_at(payload.run_time),
    )


@router.patch("/{schedule_id}")
def patch_schedule(schedule_id: str, payload: SchedulePayload):
    if not db.get_schedule(schedule_id):
        raise HTTPException(status_code=404, detail="schedule not found")
    raw_categories = ",".join(payload.categories) if isinstance(payload.categories, list) else payload.categories
    categories = parse_categories_arg(raw_categories, config.FETCH_CATEGORIES)
    return db.upsert_schedule(
        schedule_id,
        enabled=payload.enabled,
        days=payload.days,
        categories=categories,
        run_time=payload.run_time,
        next_run_at=next_run_at(payload.run_time),
    )
