"""Paper feedback APIs."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from llm import chat, extract_json
from pipeline.deep_analysis import find_paper_payload
import runtime_config
from storage import db

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


class DownvotePayload(BaseModel):
    date: str = ""
    reason: str


class UpvotePayload(BaseModel):
    date: str = ""
    reason: str = ""


def _fallback_suggestion(reason: str) -> Dict[str, Any]:
    words = [
        part.strip(" ，,.;；。").lower()
        for part in reason.replace("，", ",").replace("；", ",").split(",")
        if part.strip()
    ]
    return {
        "summary": "根据反馈生成的候选配置建议，需要人工确认。",
        "config_changes": [
            {
                "key": "BLACKLIST_KEYWORDS",
                "action": "append",
                "values": words[:5],
                "rationale": reason,
            }
        ] if words else [],
    }


def infer_feedback_suggestion(reason: str, paper: Dict[str, Any]) -> Dict[str, Any]:
    prompt = f"""
你是 Paper Radio 的偏好配置助手。用户 downvote 了一篇论文，请把理由抽取为配置修改建议。
只输出 JSON，格式：
{{
  "summary": "一句话解释",
  "config_changes": [
    {{"key": "BLACKLIST_KEYWORDS", "action": "append", "values": ["keyword"], "rationale": "原因"}}
  ]
}}
只能建议这些 key：BLACKLIST_KEYWORDS, BLACKLIST_SUBJECTS, PREFILTER_KEYWORDS, TOPICS_OF_INTEREST。
不要真的修改配置。

论文：
title={paper.get('title', '')}
abstract={paper.get('abstract', '')}
categories={paper.get('categories', [])}
topic={paper.get('topic_category', '')}

用户理由：
{reason}
"""
    try:
        text = chat(
            [{"role": "user", "content": prompt}],
            max_tokens=2000,
            tier="fast",
            label="feedback_downvote_config_suggestion",
        )
        data = extract_json(text)
        if isinstance(data, dict):
            return data
    except Exception:
        return _fallback_suggestion(reason)
    return _fallback_suggestion(reason)


@router.get("")
def list_feedback():
    return {"feedback": db.list_feedback()}


@router.post("/{arxiv_id}/downvote")
def downvote_paper(arxiv_id: str, payload: DownvotePayload):
    if not payload.reason.strip():
        raise HTTPException(status_code=400, detail="reason is required")
    paper = find_paper_payload(arxiv_id, date=payload.date) or {"arxiv_id": arxiv_id}
    suggestion = infer_feedback_suggestion(payload.reason, paper)
    item = db.create_feedback(
        arxiv_id,
        date=payload.date or paper.get("announced_day", ""),
        reason=payload.reason.strip(),
        paper=paper,
        suggestion=suggestion,
        feedback_type="downvote",
    )
    db.upsert_paper_state(
        arxiv_id,
        payload.date or paper.get("announced_day", ""),
        upvoted=False,
        downvoted=True,
    )
    return item


@router.post("/{arxiv_id}/upvote")
def upvote_paper(arxiv_id: str, payload: UpvotePayload):
    paper = find_paper_payload(arxiv_id, date=payload.date) or {"arxiv_id": arxiv_id}
    resolved_date = payload.date or paper.get("announced_day", "")
    item = db.create_feedback(
        arxiv_id,
        date=resolved_date,
        reason=payload.reason.strip() or "upvote",
        paper=paper,
        suggestion={"summary": "已记录正向反馈。", "config_changes": []},
        feedback_type="upvote",
    )
    paper_state = db.upsert_paper_state(
        arxiv_id,
        resolved_date,
        upvoted=True,
        downvoted=False,
    )
    return {"feedback": item, "state": paper_state}


@router.post("/{feedback_id}/apply")
def apply_feedback(feedback_id: int):
    item = db.get_feedback(feedback_id)
    if not item:
        raise HTTPException(status_code=404, detail="feedback not found")
    if item["status"] == "applied":
        return item

    applied = []
    for change in item.get("suggestion", {}).get("config_changes", []):
        key = change.get("key")
        if key not in runtime_config.CONFIG_SCHEMA:
            continue
        if change.get("action") == "append":
            current = runtime_config.resolved_value(key)
            values = change.get("values") or []
            if not isinstance(current, list):
                continue
            next_value = list(current)
            for value in values:
                if value and value not in next_value:
                    next_value.append(value)
            runtime_config.set_override(key, next_value, source=f"feedback:{feedback_id}")
            applied.append({"key": key, "value": next_value})
        elif change.get("action") == "set":
            runtime_config.set_override(key, change.get("value"), source=f"feedback:{feedback_id}")
            applied.append({"key": key, "value": change.get("value")})

    runtime_config.apply_overrides_to_config()
    db.update_feedback_status(feedback_id, "applied")
    return {"ok": True, "applied": applied, "feedback": db.get_feedback(feedback_id)}
