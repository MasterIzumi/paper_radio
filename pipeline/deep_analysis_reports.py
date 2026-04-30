"""File artifacts for on-demand deep analysis reports."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict

import config


def safe_paper_id(arxiv_id: str) -> str:
    """Make an arXiv id safe as one directory name."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", arxiv_id).strip("_") or "unknown"


def report_dir_for(arxiv_id: str) -> Path:
    return config.DEEP_ANALYSIS_OUTPUT_DIR / safe_paper_id(arxiv_id)


def report_path_for(arxiv_id: str) -> Path:
    return report_dir_for(arxiv_id) / "deep_analysis.md"


def write_deep_analysis_report(result: Dict[str, Any]) -> Path:
    """Persist a deep-analysis result as a human-readable Markdown artifact."""
    arxiv_id = str(result.get("arxiv_id") or "")
    path = report_path_for(arxiv_id)
    path.parent.mkdir(parents=True, exist_ok=True)

    title = str(result.get("title") or arxiv_id)
    date = str(result.get("date") or "")
    model = str(result.get("model") or "")
    generated_at = str(result.get("generated_at") or "")
    analysis = str(result.get("analysis_markdown") or "")

    content = "\n".join(
        [
            f"# {title}",
            "",
            f"- arXiv ID: `{arxiv_id}`",
            f"- arXiv URL: https://arxiv.org/abs/{arxiv_id}",
            f"- Announced Date: {date or '-'}",
            f"- Model: {model or '-'}",
            f"- Generated At: {generated_at or '-'}",
            "",
            "## Deep Analysis",
            "",
            analysis,
            "",
        ]
    )
    path.write_text(content, encoding="utf-8")
    return path
