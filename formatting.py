"""展示层共用的格式化工具。

`ranker` / `reporter` / `recent_report` / `selected_report` 之前各有一份
``_fmt_authors`` / ``_fmt_affiliations`` / ``clip`` / Markdown 转义 / arXiv id 排序 key，
行为微妙不同。统一到这里，避免后续改一处漏一处。
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Sequence, Union

from models import Paper, RankedPaper

PaperLike = Union[Paper, RankedPaper]


# ── 文本基础操作 ─────────────────────────────────────────────────────────────


def clip(text: str, width: int) -> str:
    """按可视宽度裁剪字符串，超出部分以省略号结尾。"""
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
    text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    text = text.replace("|", "\\|")
    return text


# ── 作者 / 机构 ──────────────────────────────────────────────────────────────


def _dedupe_strings(values: Iterable[str]) -> List[str]:
    deduped: List[str] = []
    for value in values:
        cleaned = str(value).strip()
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)
    return deduped


def fmt_authors(authors: Sequence[str], max_authors: int = 4) -> str:
    cleaned = [str(a).strip() for a in authors if str(a).strip()]
    if not cleaned:
        return "Unknown"
    head = ", ".join(cleaned[:max_authors])
    if len(cleaned) > max_authors:
        return f"{head} et al."
    return head


def fmt_affiliations(
    paper: PaperLike,
    *,
    max_affiliations: int = 3,
    prefer_normalized: bool = True,
) -> str:
    """把论文的机构列表格式化成展示用字符串。

    - ``prefer_normalized=True`` 时优先用 LLM 归一过的 ``normalized_institutions``；
      没有时降级到原始 ``affiliations``；再没有返回 "N/A"。
    """
    sources: List[List[str]] = []

    if prefer_normalized and isinstance(paper, RankedPaper) and paper.normalized_institutions:
        sources.append(paper.normalized_institutions)
    sources.append(paper.affiliations)

    for source in sources:
        deduped = _dedupe_strings(source)
        if not deduped:
            continue
        head = "; ".join(deduped[:max_affiliations])
        return head + " ..." if len(deduped) > max_affiliations else head

    return "N/A"


# ── 日期 ─────────────────────────────────────────────────────────────────────


_WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def weekday_cn(dt: datetime) -> str:
    return _WEEKDAY_CN[dt.weekday()]


# ── arXiv id 排序 ────────────────────────────────────────────────────────────


def arxiv_sort_key(paper: PaperLike) -> tuple[int, str]:
    """把 arxiv_id 变成可排序的 key，能兼容老版本 "旧/新" 编号。"""
    arxiv_id = paper.arxiv_id if hasattr(paper, "arxiv_id") else ""
    numeric = str(arxiv_id).replace(".", "")
    try:
        return (0, f"{int(numeric):020d}")
    except ValueError:
        return (1, str(arxiv_id))


__all__ = [
    "clip",
    "escape_md_cell",
    "fmt_authors",
    "fmt_affiliations",
    "weekday_cn",
    "arxiv_sort_key",
]
