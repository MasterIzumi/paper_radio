"""stage2 之后的评分叠加：featured authors 加分、顶会录用加分。

这一层独立于 LLM 调用，纯规则 + 正则，适合:

- 继续扩充其它加分规则，不污染 LLM prompt
- 让 `selected_papers` 快照能展示"为什么加分"（``bonus_reasons``）
- 保证 LLM 端口本身的语义不变（``relevance_score`` / ``novelty_score`` 不动）

总分公式：

    total_score = clamp(relevance + novelty + min(author + venue, BONUS_BUDGET),
                        0, TOTAL_SCORE_MAX)

注：``RankedPaper.penalty`` 字段保留为扩展点，目前恒为 0 —— 黑名单关键词已改为
在 ``ranker._rule_prefilter`` 阶段硬剔除，不再在此处降权。
"""
from __future__ import annotations

import logging
import re
from dataclasses import replace
from typing import Iterable, List, Tuple

from config import (
    AUTHOR_BONUS_CAP,
    AUTHOR_BONUS_PER_HIT,
    BONUS_BUDGET,
    FEATURED_AUTHORS,
    FEATURED_VENUES,
    TOTAL_SCORE_MAX,
    VENUE_BONUS,
)
from models import RankedPaper

logger = logging.getLogger(__name__)


# ── 作者 + 机构双命中 ─────────────────────────────────────────────────────────


def _normalize_name(raw: str) -> str:
    """把作者名压成一个便于对比的形式：去标点、多空格、整体转小写。"""
    cleaned = re.sub(r"[^\w\s]", " ", raw or "", flags=re.UNICODE)
    return re.sub(r"\s+", " ", cleaned).strip().lower()


def _collect_institution_signals(paper: RankedPaper) -> str:
    """把一篇论文所有机构线索拼成一个大字符串（小写），供 substring 匹配。"""
    parts: List[str] = []
    parts.extend(paper.normalized_institutions or [])
    parts.extend(paper.affiliations or [])
    parts.extend(paper.raw_affiliations or [])
    if paper.institution_summary:
        parts.append(paper.institution_summary)
    return " | ".join(parts).lower()


def _match_featured_authors(paper: RankedPaper) -> List[Tuple[str, str]]:
    """返回命中的 (作者官方写法, 命中到的机构关键词) 二元组列表。"""
    if not FEATURED_AUTHORS:
        return []

    paper_author_names = {_normalize_name(name) for name in paper.authors}
    institution_blob = _collect_institution_signals(paper)

    hits: List[Tuple[str, str]] = []
    for canonical_name, institution_keywords in FEATURED_AUTHORS.items():
        norm_target = _normalize_name(canonical_name)
        if norm_target not in paper_author_names:
            continue

        hit_keyword = next(
            (kw for kw in institution_keywords if kw and kw.lower() in institution_blob),
            None,
        )
        if hit_keyword is None:
            # 名字命中但机构关键词都没出现——很可能是同名冲突，不加分
            logger.debug(
                "作者名命中但机构未命中，跳过：paper=%s author=%s",
                paper.arxiv_id, canonical_name,
            )
            continue

        hits.append((canonical_name, hit_keyword))

    return hits


# ── 顶会录用识别 ──────────────────────────────────────────────────────────────


_ACCEPT_PREFIX = (
    r"(?:accept(?:ed)?|to\s+appear|appear(?:ing)?\s+in|"
    r"to\s+be\s+published|in\s+(?:proceedings|the\s+proceedings))"
)

# "前置否定词 + (可选介词) + <VENUE>"：命中这里就视为该会议不算录用
_NEGATIVE_PREFIX = (
    r"(?:submit(?:ted|ting)?|reject(?:ed)?|under\s+review|"
    r"(?:not|never)\s+accepted|declin(?:ed|ing)?)"
)


def _build_venue_patterns(venues: Iterable[str]) -> List[Tuple[str, re.Pattern, re.Pattern]]:
    """对每个会议名编译三条正则：

    A. ``accepted ... <VENUE>`` 或 ``to appear ... <VENUE>`` 等明确录用表述
    B. ``<VENUE> <YEAR>`` 直接共现（典型如 "CVPR 2024"、"NeurIPS 2023"）
    N. ``submitted/rejected/under review ... <VENUE>`` 否定上下文——命中就否决该会议

    返回 ``(venue, accept_or_year_pattern, negative_pattern)``。
    """
    compiled: List[Tuple[str, re.Pattern, re.Pattern]] = []
    for venue in venues:
        if not venue:
            continue
        v = re.escape(venue)
        pattern_a = rf"\b{_ACCEPT_PREFIX}\b[^.]{{0,60}}?\b{v}\b"
        pattern_b = rf"\b{v}\s*(?:[,\-:]|\s)?\s*(?:20\d{{2}}|'\d{{2}})"
        combined = re.compile(rf"(?:{pattern_a})|(?:{pattern_b})", re.IGNORECASE)
        negative = re.compile(
            rf"\b{_NEGATIVE_PREFIX}\b[^.]{{0,40}}?\b{v}\b",
            re.IGNORECASE,
        )
        compiled.append((venue, combined, negative))
    return compiled


_VENUE_PATTERNS = _build_venue_patterns(FEATURED_VENUES)


def _match_venues(comments: str) -> List[str]:
    """从 comments 抽出命中的顶会名单。

    策略：先用"accepted / to appear / 会议名+年份"命中，再用"submitted / rejected /
    under review"否定上下文过滤掉明显投稿未录用的场景。同一篇 comments 里同时混出
    accepted 和 rejected 多个会议时，仅剔除落在否定上下文里的那几个。
    """
    if not comments:
        return []
    text = comments.strip()
    if not text:
        return []

    hits: List[str] = []
    for venue, positive, negative in _VENUE_PATTERNS:
        if not positive.search(text):
            continue
        if negative.search(text):
            logger.debug("venue %s 命中但落在否定上下文，跳过：%s", venue, text[:120])
            continue
        hits.append(venue)
    return hits


# ── 主入口 ────────────────────────────────────────────────────────────────────


def _compute_adjustments(paper: RankedPaper) -> Tuple[int, int, int, List[str]]:
    """返回 (author_bonus, venue_bonus, penalty, bonus_reasons) 四元组。

    ``penalty`` 目前恒为 0（字段保留作扩展点），黑名单关键词已在规则预筛阶段
    硬剔除，不再在此处降权。
    """
    reasons: List[str] = []

    # ── author bonus ──
    author_hits = _match_featured_authors(paper)
    raw_author_bonus = AUTHOR_BONUS_PER_HIT * len(author_hits)
    author_bonus = min(raw_author_bonus, AUTHOR_BONUS_CAP)
    for name, kw in author_hits:
        reasons.append(f"featured author: {name}@{kw} +{AUTHOR_BONUS_PER_HIT}")
    if raw_author_bonus > AUTHOR_BONUS_CAP:
        reasons.append(f"(author_bonus 封顶 {AUTHOR_BONUS_CAP}，原始 {raw_author_bonus})")

    # ── venue bonus（同篇只加一次，展示出所有命中会议）──
    venue_hits = _match_venues(paper.comments)
    venue_bonus = VENUE_BONUS if venue_hits else 0
    if venue_hits:
        reasons.append(f"venue accepted: {', '.join(venue_hits)} +{VENUE_BONUS}")

    # ── BONUS_BUDGET 硬封顶 ──
    total_bonus = author_bonus + venue_bonus
    if total_bonus > BONUS_BUDGET:
        overflow = total_bonus - BONUS_BUDGET
        reasons.append(f"(总 bonus 封顶 {BONUS_BUDGET}，原始 {total_bonus}，截断 {overflow})")
        # 策略：先压 venue_bonus，再压 author_bonus（保护"重点作者"信号优先级）
        if venue_bonus >= overflow:
            venue_bonus -= overflow
        else:
            overflow -= venue_bonus
            venue_bonus = 0
            author_bonus = max(0, author_bonus - overflow)

    return author_bonus, venue_bonus, 0, reasons


def _rerank_by_total(papers: List[RankedPaper]) -> List[RankedPaper]:
    """按 total_score 降序 + arxiv_id 次序重排，并重写 rank。

    注意：这里直接 ``dataclasses.replace`` 只改 ``rank``，不能走 ``with_scores(rank=...)``
    否则 with_scores 会把我们刚在 with_adjustments 里算好的 total_score 覆盖回 rel+nov，
    把 bonus 擦干净。
    """
    sorted_papers = sorted(
        papers,
        key=lambda p: (p.total_score, str(p.arxiv_id).replace(".", "")),
        reverse=True,
    )
    return [replace(p, rank=i) for i, p in enumerate(sorted_papers, 1)]


def apply_score_adjustments(papers: List[RankedPaper]) -> List[RankedPaper]:
    """为一组已经 LLM 打分的论文叠加 bonus/penalty，并按新总分重排 rank。

    流程：

    1. 对每篇算 (author_bonus, venue_bonus, penalty, reasons)
    2. 调 ``paper.with_adjustments(...)``，其内部会重算 ``total_score`` 并按
       ``TOTAL_SCORE_MAX`` 截断
    3. 整批按新 total_score 重排，写回 ``rank``

    日志汇总：多少篇命中作者 / 多少篇命中顶会 / 多少篇被封顶截断。
    """
    if not papers:
        return []

    adjusted: List[RankedPaper] = []
    author_hits = venue_hits = capped = 0
    for paper in papers:
        a, v, pen, reasons = _compute_adjustments(paper)
        if a > 0:
            author_hits += 1
        if v > 0:
            venue_hits += 1
        if any(r.startswith("(") for r in reasons):
            capped += 1
        adjusted.append(
            paper.with_adjustments(
                author_bonus=a,
                venue_bonus=v,
                penalty=pen,
                bonus_reasons=reasons,
                total_score_cap=TOTAL_SCORE_MAX,
            )
        )

    reranked = _rerank_by_total(adjusted)
    logger.info(
        "评分叠加：%d 篇中 %d 篇命中 featured author，%d 篇命中顶会，%d 篇触发封顶",
        len(papers), author_hits, venue_hits, capped,
    )
    return reranked


__all__ = ["apply_score_adjustments"]
