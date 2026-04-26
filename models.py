"""论文数据模型。

整条管线用统一的 dataclass 承载论文信息，避免在字典里到处 ``.get()``：

- ``Paper``：从 arXiv 抓取并去重后的基础元信息。
- ``RankedPaper``：经过 LLM 排序后多出评分和摘要字段。

``RankedPaper`` 同时承载"TOP N 机构推断"的结果（``normalized_institutions`` 等），
因为下游（reporter）总是在同一批对象上查看评分 + 机构，所以压在一层更省心。

所有字段都保持"默认值友好"：空字符串 / 空列表 / None，方便渐进式填充。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, fields, replace
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional


# ── 时间解析 ──────────────────────────────────────────────────────────────────

_ATOM_DATETIME_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _parse_atom_datetime(value: Any) -> Optional[datetime]:
    """解析 arXiv Atom feed 的 ``YYYY-MM-DDTHH:MM:SSZ`` 时间字符串。"""
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.strptime(str(value), _ATOM_DATETIME_FMT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _parse_iso_date(value: Any) -> Optional[date]:
    """解析 ``YYYY-MM-DD`` 日期字符串（容忍前缀更长的日期时间）。"""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if not value:
        return None
    text = str(value)[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def _normalize_arxiv_id(raw: Any) -> str:
    """移除 ``vN`` 版本后缀，统一成基础 arxiv_id。"""
    text = str(raw or "").strip()
    return re.sub(r"v\d+$", "", text)


def _coerce_int(value: Any, default: int = 0) -> int:
    """LLM 打分可能给字符串 / float，这里统一转成 int。"""
    if value is None or value == "":
        return default
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _coerce_str_list(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    try:
        return [str(item).strip() for item in value if str(item).strip()]
    except TypeError:
        return []


# ── Paper ────────────────────────────────────────────────────────────────────


@dataclass
class Paper:
    """一篇 arXiv 论文的基础元信息。"""

    arxiv_id: str
    title: str = ""
    abstract: str = ""
    authors: List[str] = field(default_factory=list)
    affiliations: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    # arXiv 元信息 comments 字段（例："Accepted by CVPR 2024. 8 pages."），
    # 用于顶会录用识别；缺失或未抓到时为空串。
    comments: str = ""
    abs_url: str = ""
    pdf_url: str = ""
    # 论文的真实提交日期（arXiv API 字段）
    published: Optional[datetime] = None
    updated: Optional[datetime] = None
    # arXiv recent 页面的 announce 日期（每日统计用，不会被 API 覆盖）
    announced_date: Optional[date] = None

    # ── 反序列化 ────────────────────────────────────────────────────────────

    @classmethod
    def from_recent_entry(
        cls,
        *,
        arxiv_id: str,
        title: str = "",
        authors: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        announced_at: Optional[datetime] = None,
    ) -> "Paper":
        """从 recent 页面抓取结果构造 Paper。"""
        normalized_id = _normalize_arxiv_id(arxiv_id)
        return cls(
            arxiv_id=normalized_id,
            title=title,
            abstract="",
            authors=list(authors or []),
            affiliations=[],
            categories=list(categories or []),
            abs_url=f"https://arxiv.org/abs/{normalized_id}" if normalized_id else "",
            pdf_url=f"https://arxiv.org/pdf/{normalized_id}" if normalized_id else "",
            published=announced_at,
            updated=announced_at,
            announced_date=announced_at.date() if announced_at else None,
        )

    @classmethod
    def from_atom_entry(cls, entry: Dict[str, Any]) -> Optional["Paper"]:
        """从 arXiv Atom API 解析字典构造 Paper。

        ``entry`` 预期包含 ``arxiv_id / title / abstract / authors / affiliations /
        categories / published / updated``（字符串形态）。
        """
        arxiv_id = _normalize_arxiv_id(entry.get("arxiv_id", ""))
        title = str(entry.get("title", "")).strip()
        if not arxiv_id or not title:
            return None
        return cls(
            arxiv_id=arxiv_id,
            title=title,
            abstract=str(entry.get("abstract", "")).strip(),
            authors=_coerce_str_list(entry.get("authors")),
            affiliations=_coerce_str_list(entry.get("affiliations")),
            categories=_coerce_str_list(entry.get("categories")),
            comments=str(entry.get("comments", "")).strip(),
            abs_url=str(entry.get("abs_url", "")) or f"https://arxiv.org/abs/{arxiv_id}",
            pdf_url=str(entry.get("pdf_url", "")) or f"https://arxiv.org/pdf/{arxiv_id}",
            published=_parse_atom_datetime(entry.get("published")),
            updated=_parse_atom_datetime(entry.get("updated")),
            announced_date=_parse_iso_date(entry.get("announced_date")),
        )

    # ── 便捷属性 ────────────────────────────────────────────────────────────

    @property
    def published_day(self) -> str:
        """用于表格展示的真实提交日期（YYYY-MM-DD），空则为空串。"""
        return self.published.strftime("%Y-%m-%d") if self.published else ""

    @property
    def announced_day(self) -> str:
        """arXiv announce 日期的 YYYY-MM-DD 字符串。没有时退回 published_day。"""
        if self.announced_date:
            return self.announced_date.strftime("%Y-%m-%d")
        return self.published_day

    @property
    def primary_url(self) -> str:
        return self.abs_url or (f"https://arxiv.org/abs/{self.arxiv_id}" if self.arxiv_id else "")

    # ── 合并 ────────────────────────────────────────────────────────────────

    def merge_non_empty(self, other: "Paper") -> "Paper":
        """把 ``other`` 的非空字段合并进当前对象，返回新对象。

        语义：incoming（other）里非空的字段覆盖 existing，空字段不动。
        用于 ``_dedupe_papers`` 场景——同一篇从两分区抓到时，不能让空值擦掉已有数据。
        """
        updates: Dict[str, Any] = {}
        for f in fields(self):
            new_value = getattr(other, f.name)
            if new_value in (None, "", [], {}):
                continue
            updates[f.name] = new_value
        return replace(self, **updates)

    # ── 序列化（给 JSON 快照等低频场景用）────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return {
            "arxiv_id": self.arxiv_id,
            "title": self.title,
            "abstract": self.abstract,
            "authors": list(self.authors),
            "affiliations": list(self.affiliations),
            "categories": list(self.categories),
            "comments": self.comments,
            "abs_url": self.abs_url,
            "pdf_url": self.pdf_url,
            "published": self.published.strftime(_ATOM_DATETIME_FMT) if self.published else "",
            "updated": self.updated.strftime(_ATOM_DATETIME_FMT) if self.updated else "",
            "announced_date": self.announced_date.strftime("%Y-%m-%d") if self.announced_date else "",
        }


# ── RankedPaper ──────────────────────────────────────────────────────────────


@dataclass
class RankedPaper(Paper):
    """带 LLM 评分 / 机构推断结果的论文。"""

    # LLM 排序阶段
    relevance_score: int = 0
    novelty_score: int = 0
    total_score: int = 0
    topic_category: str = "未分类"
    one_line_summary: str = ""
    rank: int = 0

    # 机构推断阶段（TOP K 才会填）
    raw_affiliations: List[str] = field(default_factory=list)
    normalized_institutions: List[str] = field(default_factory=list)
    institution_types: str = "unknown"
    institution_summary: str = ""
    institution_evidence_source: str = "unknown"
    # 供下游诊断用，LLM 推断过的 PDF 首页文本
    pdf_first_page_context: str = ""

    # 加分/扣分叠加阶段（score_adjust.py 填写，在 stage2 之后执行）
    # total_score 的最终值 = clamp(relevance + novelty + author_bonus + venue_bonus - penalty, 0, TOTAL_SCORE_MAX)
    author_bonus: int = 0
    venue_bonus: int = 0
    penalty: int = 0
    # 人类可读的加分/扣分原因，用于日报卡片展示。每项形如 "Hongyang Li@HKU +3"、"CVPR 2024 +4"
    bonus_reasons: List[str] = field(default_factory=list)

    @classmethod
    def from_paper(cls, paper: Paper, **overrides: Any) -> "RankedPaper":
        """用一个 Paper 构造 RankedPaper，可传 LLM 字段覆盖。"""
        base_kwargs = {f.name: getattr(paper, f.name) for f in fields(Paper)}
        base_kwargs.update(overrides)
        return cls(**base_kwargs)

    def with_scores(
        self,
        *,
        relevance_score: Any = None,
        novelty_score: Any = None,
        total_score: Any = None,
        topic_category: Any = None,
        one_line_summary: Any = None,
        rank: Any = None,
    ) -> "RankedPaper":
        """返回一个打了分 / 覆盖了排序字段的新对象。"""
        rel = _coerce_int(relevance_score, self.relevance_score)
        nov = _coerce_int(novelty_score, self.novelty_score)
        total_raw = _coerce_int(total_score, -1)
        total = total_raw if total_raw >= 0 else rel + nov

        return replace(
            self,
            relevance_score=rel,
            novelty_score=nov,
            total_score=total,
            topic_category=(topic_category if topic_category else self.topic_category) or "未分类",
            one_line_summary=one_line_summary if one_line_summary is not None else self.one_line_summary,
            rank=_coerce_int(rank, self.rank),
        )

    def with_adjustments(
        self,
        *,
        author_bonus: int = 0,
        venue_bonus: int = 0,
        penalty: int = 0,
        bonus_reasons: Optional[List[str]] = None,
        total_score_cap: Optional[int] = None,
    ) -> "RankedPaper":
        """套用 bonus/penalty 并重算 total_score。

        total_score = clamp(relevance + novelty + author_bonus + venue_bonus - penalty,
                            0, total_score_cap or +∞)
        注意 rank 不在这里重排，由调用方在整批算完 total_score 后统一重排。
        """
        new_total = self.relevance_score + self.novelty_score + author_bonus + venue_bonus - penalty
        if new_total < 0:
            new_total = 0
        if total_score_cap is not None and new_total > total_score_cap:
            new_total = total_score_cap
        return replace(
            self,
            author_bonus=max(0, int(author_bonus)),
            venue_bonus=max(0, int(venue_bonus)),
            penalty=max(0, int(penalty)),
            bonus_reasons=list(bonus_reasons or []),
            total_score=new_total,
        )

    def with_institutions(
        self,
        *,
        raw_affiliations: Optional[List[str]] = None,
        normalized_institutions: Optional[List[str]] = None,
        merged_affiliations: Optional[List[str]] = None,
        institution_types: str = "unknown",
        institution_summary: str = "",
        institution_evidence_source: str = "unknown",
        pdf_first_page_context: Optional[str] = None,
    ) -> "RankedPaper":
        return replace(
            self,
            raw_affiliations=list(raw_affiliations or self.raw_affiliations),
            normalized_institutions=list(normalized_institutions or []),
            affiliations=list(merged_affiliations if merged_affiliations is not None else self.affiliations),
            institution_types=institution_types or "unknown",
            institution_summary=(institution_summary or "").strip(),
            institution_evidence_source=institution_evidence_source or "unknown",
            pdf_first_page_context=(
                pdf_first_page_context if pdf_first_page_context is not None else self.pdf_first_page_context
            ),
        )

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update(
            {
                "relevance_score": self.relevance_score,
                "novelty_score": self.novelty_score,
                "total_score": self.total_score,
                "topic_category": self.topic_category,
                "one_line_summary": self.one_line_summary,
                "rank": self.rank,
                "raw_affiliations": list(self.raw_affiliations),
                "normalized_institutions": list(self.normalized_institutions),
                "institution_types": self.institution_types,
                "institution_summary": self.institution_summary,
                "institution_evidence_source": self.institution_evidence_source,
                "pdf_first_page_context": self.pdf_first_page_context,
                "author_bonus": self.author_bonus,
                "venue_bonus": self.venue_bonus,
                "penalty": self.penalty,
                "bonus_reasons": list(self.bonus_reasons),
            }
        )
        return base


__all__ = [
    "Paper",
    "RankedPaper",
]
