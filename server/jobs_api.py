"""Background mining job APIs."""
from __future__ import annotations

import threading
import uuid
from typing import List, Union

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import config
from pipeline.run import PipelineCanceled, run_mining_pipeline
from recent_report import parse_categories_arg
from storage import db

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class JobCanceled(RuntimeError):
    pass


class MiningJobRequest(BaseModel):
    days: int = Field(default=config.DAYS_BACK, ge=1, le=30)
    categories: Union[List[str], str] = Field(default_factory=lambda: list(config.FETCH_CATEGORIES))


def _run_job(job_id: str, params: dict) -> None:
    def is_cancel_requested() -> bool:
        job = db.get_job(job_id)
        return bool(job and job.get("status") == "cancel_requested")

    def progress(message: str, value: int) -> None:
        if is_cancel_requested():
            raise JobCanceled("任务已取消")
        db.update_job(job_id, progress=value)
        db.add_job_log(job_id, message)

    try:
        job = db.get_job(job_id)
        if job and job.get("status") == "cancel_requested":
            raise JobCanceled("任务已取消")
        db.update_job(job_id, status="running", progress=1, started=True)
        db.add_job_log(job_id, "任务开始")
        result = run_mining_pipeline(
            days=int(params["days"]),
            categories=list(params["categories"]),
            auto_deep_analysis=False,
            progress_callback=progress,
            cancel_check=is_cancel_requested,
        )
        db.update_job(
            job_id,
            status="succeeded",
            progress=100,
            result=result.to_dict(),
            finished=True,
        )
        db.add_job_log(job_id, "任务完成")
    except (JobCanceled, PipelineCanceled) as exc:
        db.update_job(
            job_id,
            status="canceled",
            error=str(exc),
            finished=True,
        )
        db.add_job_log(job_id, "任务已取消", level="warning")
    except Exception as exc:
        db.update_job(
            job_id,
            status="failed",
            error=str(exc),
            finished=True,
        )
        db.add_job_log(job_id, f"任务失败：{exc}", level="error")


@router.post("/mining")
def create_mining_job(request: MiningJobRequest):
    if db.has_running_job("mining"):
        raise HTTPException(status_code=409, detail="已有 mining 任务正在运行")

    raw_categories = (
        ",".join(request.categories)
        if isinstance(request.categories, list)
        else request.categories
    )
    categories = parse_categories_arg(raw_categories, config.FETCH_CATEGORIES)
    job_id = uuid.uuid4().hex
    params = {"days": request.days, "categories": categories}
    db.create_job(job_id, "mining", params)

    thread = threading.Thread(target=_run_job, args=(job_id, params), daemon=True)
    thread.start()
    return {"job_id": job_id, "status": "queued"}


@router.get("")
def list_jobs():
    return {"jobs": db.list_jobs()}


@router.get("/{job_id}")
def get_job(job_id: str):
    item = db.get_job(job_id)
    if not item:
        raise HTTPException(status_code=404, detail="job not found")
    return item


@router.get("/{job_id}/logs")
def get_job_logs(job_id: str):
    if not db.get_job(job_id):
        raise HTTPException(status_code=404, detail="job not found")
    return {"logs": db.list_job_logs(job_id)}


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str):
    item = db.get_job(job_id)
    if not item:
        raise HTTPException(status_code=404, detail="job not found")
    if item["status"] not in ("queued", "running", "cancel_requested"):
        return item
    db.update_job(job_id, status="cancel_requested")
    db.add_job_log(job_id, "收到取消请求，当前步骤结束后停止", level="warning")
    return db.get_job(job_id)


@router.post("/mining/reset-active")
def reset_active_mining_jobs():
    count = db.reset_active_jobs("mining")
    return {"ok": True, "reset_count": count}
