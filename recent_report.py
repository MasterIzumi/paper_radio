"""最近论文抓取结果的表格渲染与 Markdown 输出工具。"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, List, Sequence


def parse_categories_arg(raw: str, default_categories: Sequence[str]) -> List[str]:
    categories = [item.strip() for item in raw.split(",") if item.strip()]
    return categories or list(default_categories)


def fmt_authors(authors: List[str], max_authors: int = 4) -> str:
    if not authors:
        return "Unknown"

    head = ", ".join(authors[:max_authors])
    if len(authors) > max_authors:
        return f"{head} et al."
    return head


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


def clip(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    if width <= 1:
        return text[:width]
    return text[: width - 1] + "…"


def escape_md_cell(value: object) -> str:
    """转义 Markdown 表格单元格，避免 ``|`` / 换行破坏表格结构。"""
    if value is None:
        return ""
    text = str(value)
    # 换行会撕开表格，先压成空格
    text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    # 管道符统一转义
    text = text.replace("|", "\\|")
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


def weekday_cn(dt: datetime) -> str:
    names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    return names[dt.weekday()]


def build_daily_counts_by_category(
    papers: List[dict],
    days_back: int,
    categories: List[str],
    now: datetime | None = None,
) -> tuple[List[str], List[List[str]]]:
    now = now or datetime.now()
    counts: dict[str, dict[str, int]] = {}

    for paper in papers:
        published = paper.get("published", "")[:10]
        if not published:
            continue

        day_counts = counts.setdefault(published, {})
        day_counts["_total"] = day_counts.get("_total", 0) + 1

        paper_categories = paper.get("categories", [])
        matched = set()
        for configured in categories:
            for value in paper_categories:
                if configured in value:
                    matched.add(configured)
                    break

        if not matched:
            matched.add("other")

        for category in matched:
            day_counts[category] = day_counts.get(category, 0) + 1

    headers = ["日期", "星期", "总量", *categories]
    rows: List[List[str]] = []
    for offset in range(days_back):
        day = now - timedelta(days=offset)
        day_str = day.strftime("%Y-%m-%d")
        day_counts = counts.get(day_str, {})
        row = [
            day.strftime("%m.%d"),
            weekday_cn(day),
            str(day_counts.get("_total", 0)),
        ]
        row.extend(str(day_counts.get(category, 0)) for category in categories)
        rows.append(row)

    return headers, rows


def arxiv_sort_key(paper: dict) -> tuple[int, str]:
    arxiv_id = paper.get("arxiv_id", "")
    numeric = arxiv_id.replace(".", "")
    try:
        return (0, f"{int(numeric):020d}")
    except ValueError:
        return (1, arxiv_id)


def build_paper_table_rows(papers: List[dict]) -> List[List[str]]:
    sorted_papers = sorted(papers, key=arxiv_sort_key, reverse=True)
    rows: List[List[str]] = []
    for index, paper in enumerate(sorted_papers, 1):
        rows.append(
            [
                str(index),
                paper.get("arxiv_id", ""),
                paper.get("title", ""),
                clip(fmt_authors(paper.get("authors", [])), 38),
                clip(fmt_subjects(paper.get("categories", [])), 42),
                paper.get("abs_url", "") or f"https://arxiv.org/abs/{paper.get('arxiv_id', '')}",
                paper.get("published", "")[:10] or "N/A",
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
) -> str:
    lines = [
        f"# arXiv Recent Crawl | {now.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        f"- 查询范围：最近 {days_back} 个自然日",
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
    papers: List[dict],
    coverage_note: str = "",
) -> Path:
    daily_headers, daily_rows = build_daily_counts_by_category(papers, days_back, categories, now=now)
    daily_table = render_table(daily_rows, headers=daily_headers)
    paper_table = render_table(
        build_paper_table_rows(papers),
        headers=["#", "arXiv ID", "Title", "Authors", "Subjects", "URL", "Published"],
    )
    content = build_recent_crawl_markdown(
        now=now,
        days_back=days_back,
        categories=categories,
        paper_count=len(papers),
        daily_table=daily_table,
        paper_table=paper_table,
        coverage_note=coverage_note,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / build_recent_crawl_filename(now)
    output_path.write_text(content, encoding="utf-8")
    return output_path
