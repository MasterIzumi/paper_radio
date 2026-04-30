"""Report JSON read APIs."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

import config

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _read_json(path):
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/index")
def get_reports_index():
    return _read_json(config.REPORTS_JSON_DIR / "index.json")


@router.get("/daily/{date}")
def get_daily_report(date: str):
    return _read_json(config.DAILY_JSON_OUTPUT_DIR / f"daily_report_{date}.json")


@router.get("/selected/{date}")
def get_selected_report(date: str):
    return _read_json(config.SELECTED_JSON_OUTPUT_DIR / f"selected_papers_{date}.json")

