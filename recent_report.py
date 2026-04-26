"""最近论文抓取结果的表格渲染与 Markdown 输出工具。"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Sequence

from formatting import (
    arxiv_sort_key,
    clip,
    escape_md_cell,
    fmt_authors,
    weekday_cn,
)
from models import Paper


def parse_categories_arg(raw: str, default_categories: Sequence[str]) -> List[str]:
    categories = [item.strip() for item in raw.split(",") if item.strip()]
    return categories or list(default_categories)


def fmt_subjects(subjects: List[str], max_subjects: int = 3) -> str:
    if not subjects:
        return "N/A"

    normalized: List[str] = []
    for subject in subjects:
        match = re.search(r"\(([A-Za-z0-9.\-]+)\)", subject)
        normalized.append(match.group(1) if match else subject)

    head = normalized[:max_subjects]
    text = ", ".join(head)
    if len(normalized) > max_subjects:
        return f"{text} ..."
    return text


def render_table(rows: Iterable[List[str]], headers: List[str]) -> str:
    escaped_headers = [escape_md_cell(h) for h in headers]
    escaped_rows = [[escape_md_cell(cell) for cell in row] for row in rows]
    all_rows = [escaped_headers, *escaped_rows]
    widths = [max(len(row[i]) for row in all_rows) for i in range(len(escaped_headers))]

    def render_row(row: List[str]) -> str:
        return "| " + " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)) + " |"

    separator = "|-" + "-|-".join("-" * width for width in widths) + "-|"
    lines = [render_row(escaped_headers), separator]
    lines.extend(render_row(row) for row in escaped_rows)
    return "\n".join(lines)


def _bucket_date(paper: Paper) -> str:
    """按 announce 日期分桶，没有时退回 published 日期字符串。"""
    return paper.announced_day


def summarize_daily_counts(papers: Iterable[Paper]) -> List[tuple[str, int]]:
    """按 announce 日期聚合 ``(YYYY-MM-DD, count)``，日期倒序。"""
    buckets: dict[str, int] = {}
    for paper in papers:
        day = _bucket_date(paper)
        if not day:
            continue
        buckets[day] = buckets.get(day, 0) + 1
    return sorted(buckets.items(), key=lambda item: item[0], reverse=True)


def build_daily_counts_by_category(
    papers: List[Paper],
    days_back: int,
    categories: List[str],
    now: datetime | None = None,
) -> tuple[List[str], List[List[str]]]:
    now = now or datetime.now()
    counts: dict[str, dict[str, int]] = {}

    for paper in papers:
        bucket_day = _bucket_date(paper)
        if not bucket_day:
            continue

        day_counts = counts.setdefault(bucket_day, {})
        day_counts["_total"] = day_counts.get("_total", 0) + 1

        matched: set[str] = set()
        for configured in categories:
            for value in paper.categories:
                if configured in value:
                    matched.add(configured)
                    break

        if not matched:
            matched.add("other")

        for category in matched:
            day_counts[category] = day_counts.get(category, 0) + 1

    # 统计行：按实际出现过的 announce 日期倒序渲染。窗口由 crawler 负责裁剪，
    # 这里不再做二次过滤，避免两处时区 / 日历算法不一致引发数字对不上。
    headers = ["日期", "星期", "总量", *categories]
    rows: List[List[str]] = []
    for day_str in sorted(counts.keys(), reverse=True):
        try:
            day = datetime.strptime(day_str, "%Y-%m-%d")
        except ValueError:
            continue
        day_counts = counts[day_str]
        row = [
            day.strftime("%m.%d"),
            weekday_cn(day),
            str(day_counts.get("_total", 0)),
        ]
        row.extend(str(day_counts.get(category, 0)) for category in categories)
        rows.append(row)

    return headers, rows


def build_paper_table_rows(papers: List[Paper]) -> List[List[str]]:
    sorted_papers = sorted(papers, key=arxiv_sort_key, reverse=True)
    rows: List[List[str]] = []
    for index, paper in enumerate(sorted_papers, 1):
        rows.append(
            [
                str(index),
                paper.arxiv_id,
                paper.title,
                clip(fmt_authors(paper.authors), 38),
                clip(fmt_subjects(paper.categories), 42),
                paper.primary_url,
                paper.announced_day or "N/A",
                paper.published_day or "-",
            ]
        )
    return rows


def build_recent_crawl_filename(now: datetime) -> str:
    return f"recent_crawl_{now.strftime('%Y-%m-%d')}.md"


def build_recent_crawl_markdown(
    now: datetime,
    days_back: int,
    categories: List[str],
    paper_count: int,
    daily_table: str,
    paper_table: str,
    coverage_note: str = "",
    date_range: str = "",
) -> str:
    lines = [
        f"# arXiv Recent Crawl | {now.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        f"- 查询范围：最近 {days_back} 个自然日"
        + (f"（{date_range}）" if date_range else ""),
        f"- 分区：{', '.join(categories)}",
        f"- 论文总量：{paper_count}",
    ]

    if coverage_note:
        lines.extend(["", f"> {coverage_note}"])

    lines.extend(
        [
            "",
            "## 每日统计",
            "",
            daily_table,
            "",
            "## 论文列表",
            "",
            paper_table,
            "",
        ]
    )
    return "\n".join(lines)


def save_recent_crawl_report(
    output_dir: Path,
    now: datetime,
    days_back: int,
    categories: List[str],
    papers: List[Paper],
    coverage_note: str = "",
    date_range: str = "",
) -> Path:
    daily_headers, daily_rows = build_daily_counts_by_category(papers, days_back, categories, now=now)
    daily_table = render_table(daily_rows, headers=daily_headers)
    paper_table = render_table(
        build_paper_table_rows(papers),
        headers=["#", "arXiv ID", "Title", "Authors", "Subjects", "URL", "Announced", "Published"],
    )
    content = build_recent_crawl_markdown(
        now=now,
        days_back=days_back,
        categories=categories,
        paper_count=len(papers),
        daily_table=daily_table,
        paper_table=paper_table,
        coverage_note=coverage_note,
        date_range=date_range,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / build_recent_crawl_filename(now)
    output_path.write_text(content, encoding="utf-8")
    return output_path
