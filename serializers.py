"""结构化 JSON 导出工具。

给静态前端提供稳定的数据产物，避免前端反向解析 Markdown。
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from formatting import fmt_affiliations, fmt_authors
from models import RankedPaper


def _iso_now(now: Optional[datetime] = None) -> str:
    return (now or datetime.now()).strftime("%Y-%m-%dT%H:%M:%S")


def _paper_payload(paper: RankedPaper, *, include_institution_fields: bool = False) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "arxiv_id": paper.arxiv_id,
        "title": paper.title,
        "abstract": paper.abstract,
        "authors": list(paper.authors),
        "authors_display": fmt_authors(paper.authors, max_authors=8),
        "affiliations": list(paper.affiliations),
        "affiliations_display": fmt_affiliations(paper, max_affiliations=8),
        "categories": list(paper.categories),
        "comments": paper.comments,
        "topic_category": paper.topic_category or "未分类",
        "rank": paper.rank,
        "relevance_score": paper.relevance_score,
        "novelty_score": paper.novelty_score,
        "total_score": paper.total_score,
        "author_bonus": paper.author_bonus,
        "venue_bonus": paper.venue_bonus,
        "penalty": paper.penalty,
        "bonus_reasons": list(paper.bonus_reasons),
        "one_line_summary": paper.one_line_summary,
        "display_day": paper.announced_day,
        "published_day": paper.published_day,
        "announced_day": paper.announced_day,
        "primary_url": paper.primary_url,
        "abs_url": paper.abs_url,
        "pdf_url": paper.pdf_url,
    }
    if include_institution_fields:
        payload.update(
            {
                "raw_affiliations": list(paper.raw_affiliations),
                "normalized_institutions": list(paper.normalized_institutions),
                "institution_types": paper.institution_types,
                "institution_summary": paper.institution_summary,
                "institution_evidence_source": paper.institution_evidence_source,
            }
        )
    return payload


def _topic_summary_payload(ranked_papers: Sequence[RankedPaper]) -> List[Dict[str, Any]]:
    counter = Counter((paper.topic_category or "未分类") for paper in ranked_papers)
    return [
        {"topic_category": topic, "count": count}
        for topic, count in counter.most_common()
    ]


def build_selected_json_payload(
    *,
    now: datetime,
    ranked_papers: Sequence[RankedPaper],
    categories: Sequence[str],
    report_date: str | None = None,
) -> Dict[str, Any]:
    papers = sorted(
        ranked_papers,
        key=lambda paper: (
            -paper.total_score,
            -paper.relevance_score,
            -paper.novelty_score,
            paper.rank or 10**9,
            paper.arxiv_id,
        ),
    )
    return {
        "kind": "selected_papers",
        "date": report_date or now.strftime("%Y-%m-%d"),
        "generated_at": _iso_now(now),
        "categories": list(categories),
        "selected_paper_count": len(ranked_papers),
        "topic_summary": _topic_summary_payload(ranked_papers),
        "papers": [
            _paper_payload(paper, include_institution_fields=True)
            for paper in papers
        ],
    }


def build_daily_json_payload(
    *,
    now: datetime,
    categories: Sequence[str],
    fast_model: str,
    strong_model: str,
    ranked_papers: Sequence[RankedPaper],
    top_display_papers: Sequence[RankedPaper],
    deep_analysis_entries: Sequence[Dict[str, Any]],
    top_display_min_score: int,
    top_display_min_count: int,
    deep_analysis_max_papers: int,
    deep_analysis_min_total_score: int,
    report_date: str | None = None,
) -> Dict[str, Any]:
    deep_papers_by_id = {
        entry["paper"].arxiv_id: entry
        for entry in deep_analysis_entries
        if isinstance(entry.get("paper"), RankedPaper)
    }
    return {
        "kind": "daily_report",
        "date": report_date or now.strftime("%Y-%m-%d"),
        "generated_at": _iso_now(now),
        "categories": list(categories),
        "models": {
            "fast": fast_model,
            "strong": strong_model,
        },
        "selected_paper_count": len(ranked_papers),
        "focus_topics": [
            "端到端自动驾驶",
            "世界模型",
            "VLA 模型",
            "空间智能",
            "自动驾驶大模型",
        ],
        "display_policy": {
            "top_display_min_score": top_display_min_score,
            "top_display_min_count": top_display_min_count,
        },
        "deep_analysis_policy": {
            "max_papers": deep_analysis_max_papers,
            "min_total_score": deep_analysis_min_total_score,
        },
        "top_display_papers": [
            _paper_payload(paper, include_institution_fields=True)
            for paper in top_display_papers
        ],
        "deep_analysis_papers": [
            {
                **_paper_payload(entry["paper"], include_institution_fields=True),
                "analysis_markdown": entry["analysis"],
            }
            for entry in deep_analysis_entries
        ],
        "deep_analysis_body": "\n\n".join(
            entry["analysis"] for entry in deep_analysis_entries if entry.get("analysis")
        ),
        "top_display_details": [
            {
                **_paper_payload(paper, include_institution_fields=True),
                "analysis_markdown": (
                    deep_papers_by_id[paper.arxiv_id]["analysis"]
                    if paper.arxiv_id in deep_papers_by_id
                    else ""
                ),
            }
            for paper in top_display_papers
        ],
    }


def write_json(path: Path, payload: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_date_from_filename(path: Path) -> str:
    stem = path.stem
    for token in stem.split("_"):
        if len(token) == 10 and token[4] == "-" and token[7] == "-":
            return token
    return ""


def refresh_reports_index(
    *,
    index_path: Path,
    daily_dir: Path,
    selected_dir: Path,
    categories: Sequence[str],
) -> Path:
    entries_by_date: Dict[str, Dict[str, Any]] = {}

    for path in sorted(daily_dir.glob("daily_report_*.json")):
        date = _extract_date_from_filename(path)
        if not date:
            continue
        payload = _load_json(path)
        entry = entries_by_date.setdefault(date, {"date": date})
        entry["daily_path"] = str(path.relative_to(index_path.parent))
        entry["categories"] = payload.get("categories") or entry.get("categories") or list(categories)
        entry["daily_generated_at"] = payload.get("generated_at", "")

    for path in sorted(selected_dir.glob("selected_papers_*.json")):
        date = _extract_date_from_filename(path)
        if not date:
            continue
        payload = _load_json(path)
        entry = entries_by_date.setdefault(date, {"date": date})
        entry["selected_path"] = str(path.relative_to(index_path.parent))
        entry["categories"] = payload.get("categories") or entry.get("categories") or list(categories)
        entry["selected_generated_at"] = payload.get("generated_at", "")

    entries = sorted(entries_by_date.values(), key=lambda item: item["date"], reverse=True)
    payload = {
        "kind": "reports_index",
        "generated_at": _iso_now(),
        "default_date": entries[0]["date"] if entries else "",
        "categories": list(categories),
        "entries": entries,
    }
    return write_json(index_path, payload)
