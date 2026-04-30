"""On-demand deep analysis for one paper."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import config
import prompts
from formatting import fmt_affiliations, fmt_authors
from fulltext import fetch_sections
from llm import chat, get_active_model
from models import RankedPaper, _parse_iso_date
from pipeline.deep_analysis_reports import write_deep_analysis_report


def _ranked_from_payload(payload: Dict[str, Any]) -> RankedPaper:
    return RankedPaper(
        arxiv_id=str(payload.get("arxiv_id", "")),
        title=str(payload.get("title", "")),
        abstract=str(payload.get("abstract", "")),
        authors=list(payload.get("authors") or []),
        affiliations=list(payload.get("affiliations") or []),
        categories=list(payload.get("categories") or []),
        comments=str(payload.get("comments", "")),
        abs_url=str(payload.get("abs_url", "")),
        pdf_url=str(payload.get("pdf_url", "")),
        announced_date=_parse_iso_date(payload.get("announced_day")),
        relevance_score=int(payload.get("relevance_score") or 0),
        novelty_score=int(payload.get("novelty_score") or 0),
        total_score=int(payload.get("total_score") or 0),
        topic_category=str(payload.get("topic_category", "未分类") or "未分类"),
        one_line_summary=str(payload.get("one_line_summary", "")),
        rank=int(payload.get("rank") or 0),
        raw_affiliations=list(payload.get("raw_affiliations") or []),
        normalized_institutions=list(payload.get("normalized_institutions") or []),
        institution_types=str(payload.get("institution_types", "unknown") or "unknown"),
        institution_summary=str(payload.get("institution_summary", "")),
        institution_evidence_source=str(payload.get("institution_evidence_source", "unknown") or "unknown"),
        author_bonus=int(payload.get("author_bonus") or 0),
        venue_bonus=int(payload.get("venue_bonus") or 0),
        penalty=int(payload.get("penalty") or 0),
        bonus_reasons=list(payload.get("bonus_reasons") or []),
    )


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def find_paper_payload(arxiv_id: str, date: str = "") -> Optional[Dict[str, Any]]:
    """Find a paper in selected/daily JSON products."""
    candidates = []
    if date:
        candidates.extend(
            [
                config.SELECTED_JSON_OUTPUT_DIR / f"selected_papers_{date}.json",
                config.DAILY_JSON_OUTPUT_DIR / f"daily_report_{date}.json",
            ]
        )
    candidates.extend(sorted(config.SELECTED_JSON_OUTPUT_DIR.glob("selected_papers_*.json"), reverse=True))
    candidates.extend(sorted(config.DAILY_JSON_OUTPUT_DIR.glob("daily_report_*.json"), reverse=True))

    seen: set[Path] = set()
    for path in candidates:
        if path in seen or not path.exists():
            continue
        seen.add(path)
        payload = _load_json(path)
        for key in ("papers", "top_display_papers", "top_display_details", "deep_analysis_papers"):
            for paper in payload.get(key) or []:
                if str(paper.get("arxiv_id", "")) == arxiv_id:
                    return paper
    return None


def run_deep_analysis_for_paper(arxiv_id: str, date: str = "") -> Dict[str, Any]:
    payload = find_paper_payload(arxiv_id, date=date)
    if not payload:
        raise ValueError(f"未在现有 reports_json 中找到论文 {arxiv_id}")

    paper = _ranked_from_payload(payload)
    fulltext = fetch_sections(paper.arxiv_id)
    if fulltext:
        content_label = "正文节选（Introduction / Method）"
        content_body = fulltext
    else:
        content_label = "摘要（未找到 HTML 全文）"
        content_body = paper.abstract

    prompt = prompts.render(
        "deep_analysis",
        title=paper.title,
        authors=fmt_authors(paper.authors),
        affiliations=fmt_affiliations(paper),
        topic_category=paper.topic_category,
        content_label=content_label,
        content_body=content_body,
    )
    use_thinking = config.LLM_PROVIDER == "anthropic"
    analysis = chat(
        [{"role": "user", "content": prompt}],
        max_tokens=16000,
        thinking=use_thinking,
        tier="strong",
        label="deep_analysis:on_demand",
    ).strip()
    result = {
        "arxiv_id": arxiv_id,
        "date": date or paper.announced_day,
        "title": paper.title,
        "model": get_active_model("strong"),
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "analysis_markdown": analysis,
    }
    report_path = write_deep_analysis_report(result)
    result["report_path"] = str(report_path)
    return result
