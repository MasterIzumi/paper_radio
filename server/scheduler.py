"""Tiny in-process scheduler for dashboard mining jobs."""
from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Callable

from storage import db

_started = False


def next_run_at(run_time: str, now: datetime | None = None) -> str:
    now = now or datetime.now()
    try:
        hour, minute = [int(part) for part in run_time.split(":", 1)]
    except Exception:
        hour, minute = 9, 0
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate.strftime("%Y-%m-%dT%H:%M:%S")


def ensure_default_schedule(default_categories: list[str]) -> None:
    if db.get_schedule("daily-mining"):
        return
    db.upsert_schedule(
        "daily-mining",
        name="Daily mining",
        enabled=False,
        days=1,
        categories=default_categories,
        run_time="09:00",
        next_run_at=next_run_at("09:00"),
    )


def start_scheduler(create_job: Callable[[int, list[str], str], str]) -> None:
    global _started
    if _started:
        return
    _started = True

    def loop() -> None:
        while True:
            now = datetime.now()
            for schedule in db.list_schedules():
                if not schedule["enabled"]:
                    continue
                due = schedule.get("next_run_at") or next_run_at(schedule.get("run_time", "09:00"))
                if due > now.strftime("%Y-%m-%dT%H:%M:%S"):
                    continue
                if db.has_running_job("mining"):
                    job_id = uuid.uuid4().hex
                    db.create_job(
                        job_id,
                        "mining",
                        {
                            "days": int(schedule["days"]),
                            "categories": list(schedule["categories"]),
                            "source": "scheduled",
                            "schedule_id": schedule["id"],
                        },
                    )
                    db.update_job(
                        job_id,
                        status="canceled",
                        error="定时触发时已有 mining 任务运行，已跳过本次",
                        finished=True,
                    )
                    db.add_job_log(job_id, "已有 mining 任务运行，跳过本次定时挖掘", level="warning")
                    db.set_schedule_run_times(
                        schedule["id"],
                        next_run_at=next_run_at(schedule.get("run_time", "09:00"), now=now),
                    )
                    continue
                create_job(int(schedule["days"]), list(schedule["categories"]), "scheduled")
                db.set_schedule_run_times(
                    schedule["id"],
                    last_run_at=now.strftime("%Y-%m-%dT%H:%M:%S"),
                    next_run_at=next_run_at(schedule.get("run_time", "09:00"), now=now),
                )
            time.sleep(30)

    threading.Thread(target=loop, daemon=True).start()
