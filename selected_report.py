"""入选论文快照的渲染与 Markdown 输出工具。"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import List

from formatting import arxiv_sort_key, clip, fmt_authors
from models import RankedPaper
from recent_report import render_table


def _fmt_institutions(paper: RankedPaper) -> str:
    """机构列显示值：优先 normalized_institutions，再 fallback 到 summary / '-'。"""
    if paper.normalized_institutions:
        return clip(" / ".join(paper.normalized_institutions), 48)
    if paper.institution_summary:
        return clip(paper.institution_summary, 48)
    return "-"


def _fmt_bonus(paper: RankedPaper, attr: str) -> str:
    """格式化加分列（author_bonus / venue_bonus 等），展示 +N；零值或缺失显示 '-'。"""
    value = getattr(paper, attr, None)
    if value in (None, 0):
        return "-"
    return f"+{abs(int(value))}"


def _ranked_sort_key(paper: RankedPaper) -> tuple[int, tuple[int, str]]:
    return (paper.total_score, arxiv_sort_key(paper))


def build_selected_filename(now: datetime) -> str:
    return f"selected_papers_{now.strftime('%Y-%m-%d')}.md"


def build_selected_filename_for_date(report_date: str) -> str:
    return f"selected_papers_{report_date}.md"


def build_selected_summary_table(ranked_papers: List[RankedPaper]) -> str:
    counter = Counter((paper.topic_category or "未分类") for paper in ranked_papers)
    rows = [[topic, str(count)] for topic, count in counter.most_common()]
    return render_table(rows, headers=["方向", "数量"])


def build_selected_paper_rows(ranked_papers: List[RankedPaper]) -> List[List[str]]:
    sorted_papers = sorted(ranked_papers, key=_ranked_sort_key, reverse=True)
    rows: List[List[str]] = []
    for index, paper in enumerate(sorted_papers, 1):
        rows.append(
            [
                str(index),
                paper.arxiv_id,
                paper.title,
                paper.topic_category or "未分类",
                str(paper.total_score),
                str(paper.relevance_score),
                str(paper.novelty_score),
                _fmt_bonus(paper, "author_bonus"),
                _fmt_bonus(paper, "venue_bonus"),
                paper.one_line_summary,
                paper.announced_day or "N/A",
                _fmt_institutions(paper),
                clip(fmt_authors(paper.authors), 38),
                paper.primary_url,
            ]
        )
    return rows


def build_selected_markdown(
    now: datetime,
    ranked_papers: List[RankedPaper],
    *,
    report_date: str | None = None,
) -> str:
    summary_table = build_selected_summary_table(ranked_papers)
    paper_table = render_table(
        build_selected_paper_rows(ranked_papers),
        headers=[
            "#",
            "arXiv ID",
            "Title",
            "方向",
            "总分",
            "相关性",
            "新颖性",
            "作者加分",
            "顶会加分",
            "一句话总结",
            "Announced",
            "机构",
            "Authors",
            "URL",
        ],
    )

    lines = [
        f"# Selected Papers Snapshot | {report_date or now.strftime('%Y-%m-%d')}",
        "",
        f"- 生成时间：{now.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 入选论文数：{len(ranked_papers)}",
        "",
        "## 方向汇总",
        "",
        summary_table,
        "",
        "## 入选论文列表",
        "",
        paper_table,
        "",
    ]
    return "\n".join(lines)


def save_selected_report(
    output_dir: Path,
    now: datetime,
    ranked_papers: List[RankedPaper],
    *,
    report_date: str | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = build_selected_filename_for_date(report_date) if report_date else build_selected_filename(now)
    output_path = output_dir / filename
    content = build_selected_markdown(now, ranked_papers, report_date=report_date)
    output_path.write_text(content, encoding="utf-8")
    return output_path
