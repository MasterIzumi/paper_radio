"""使用 LLM 对论文进行筛选与排序。"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional

import prompts
from config import MAX_PAPERS_TO_RANK, TOPICS_OF_INTEREST, TOTAL_SCORE_MAX
from formatting import fmt_affiliations, fmt_authors
from llm import chat, extract_json
from models import Paper, RankedPaper
from pdf_context import fetch_pdf_first_page_context

logger = logging.getLogger(__name__)

# 第一阶段：仅凭标题快速过滤，保留候选数量
STAGE1_KEEP = 30
TOP_N = 10
PREFILTER_KEYWORDS = [
    "autonomous driving", "driving", "driverless", "end-to-end", "e2e",
    "world model", "world models", "video prediction", "occupancy",
    "bev", "4d", "spatial", "3d", "gaussian", "reconstruction",
    "depth estimation", "slam", "localization", "navigation",
    "robot", "robotics", "manipulation", "grasp", "humanoid", "locomotion",
    "vision-language-action", "vla", "policy", "planning",
    "multimodal", "scene understanding",
]


# ── 工具函数 ──────────────────────────────────────────────────────────────────


def _default_summary(paper: Paper) -> str:
    abstract = paper.abstract.strip()
    if abstract:
        first = re.split(r"(?<=[.!?。！？])\s+", abstract)[0].strip()
        if first:
            return first[:120]
    return paper.title or "N/A"


def _dedupe_strings(values: List[str]) -> List[str]:
    deduped: List[str] = []
    for value in values:
        cleaned = str(value).strip()
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)
    return deduped


# ── 规则预筛 ─────────────────────────────────────────────────────────────────


def _rule_prefilter(papers: List[Paper]) -> List[Paper]:
    """先用本地规则预筛，减少全部标题直接送给 LLM。"""
    result: List[Paper] = []
    for paper in papers[:MAX_PAPERS_TO_RANK]:
        text = " ".join([paper.title, paper.abstract, " ".join(paper.categories)]).lower()
        if any(keyword in text for keyword in PREFILTER_KEYWORDS):
            result.append(paper)

    if not result:
        fallback = papers[: min(STAGE1_KEEP * 2, len(papers))]
        logger.info("规则预筛未命中，回退保留前 %d 篇进入标题粗筛", len(fallback))
        return fallback

    logger.info(
        "规则预筛：%d → %d 篇",
        min(len(papers), MAX_PAPERS_TO_RANK), len(result),
    )
    return result


# ── 第一阶段：标题粗筛 ─────────────────────────────────────────────────────────


def _stage1_filter(papers: List[Paper]) -> List[Paper]:
    """仅发送标题，让 LLM 快速判断相关性，返回候选列表。"""
    title_lines = "\n".join(
        f"[{i}] {p.arxiv_id} | {p.title}"
        for i, p in enumerate(papers[:MAX_PAPERS_TO_RANK], 1)
    )

    prompt = prompts.render(
        "stage1_title_filter",
        topics_of_interest=TOPICS_OF_INTEREST,
        title_lines=title_lines,
        stage1_keep=STAGE1_KEEP,
    )

    try:
        logger.info("阶段1/3 标题粗筛：向 LLM 发送 %d 篇标题...", len(papers))
        raw = chat(
            [{"role": "user", "content": prompt}],
            max_tokens=16000,
            label="stage1_title_filter",
        )
        data = extract_json(raw, list_roots=("relevant_ids",))
        ids = set(data.get("relevant_ids") or data.get("items") or [])
        result = [p for p in papers if p.arxiv_id in ids]
        logger.info(
            "阶段1/3 标题粗筛完成：%d → %d 篇候选", len(papers), len(result)
        )
        return result if result else papers[:STAGE1_KEEP]
    except Exception as exc:
        logger.warning(
            "阶段1/3 标题粗筛失败（%s），直接取前 %d 篇", exc, STAGE1_KEEP
        )
        return papers[:STAGE1_KEEP]


# ── 机构推断（PDF 首页 + LLM）────────────────────────────────────────────────


def _stage_infer_institutions(
    papers: List[RankedPaper], stage_label: str = "机构推断"
) -> List[RankedPaper]:
    """对给定论文集合执行 PDF 驱动的机构归一分析。"""
    if not papers:
        return []

    paper_blocks_list = []
    for index, paper in enumerate(papers, 1):
        pdf_context = (paper.pdf_first_page_context or "").strip()
        paper_blocks_list.append(
            f"[{index}] ID:{paper.arxiv_id}\n"
            f"Title: {paper.title}\n"
            f"Authors: {fmt_authors(paper.authors)}\n"
            f"Raw Affiliations: {fmt_affiliations(paper, max_affiliations=6, prefer_normalized=False)}\n"
            f"PDF First Page Context: {pdf_context or 'N/A'}\n"
        )

    prompt = prompts.render(
        "institution_inference",
        topics_of_interest=TOPICS_OF_INTEREST,
        paper_blocks="\n".join(paper_blocks_list),
    )

    try:
        logger.info("%s：正在归一 %d 篇论文的机构信息...", stage_label, len(papers))
        raw = chat(
            [{"role": "user", "content": prompt}],
            max_tokens=8000,
            label="institution_inference",
        )
        data = extract_json(raw, list_roots=("analyses",))
    except Exception as exc:
        logger.warning("%s失败（%s），继续使用原始 affiliations", stage_label, exc)
        return papers

    analyses_by_id: Dict[str, Dict] = {}
    for item in data.get("analyses") or data.get("items") or []:
        if isinstance(item, dict):
            arxiv_id = str(item.get("arxiv_id", ""))
            if arxiv_id:
                analyses_by_id[arxiv_id] = item

    enriched: List[RankedPaper] = []
    for paper in papers:
        analysis = analyses_by_id.get(paper.arxiv_id)
        if not analysis:
            enriched.append(paper)
            continue

        normalized_list = analysis.get("normalized_institutions", [])
        if not isinstance(normalized_list, list):
            normalized_list = []
        normalized_institutions = _dedupe_strings(normalized_list)
        raw_affiliations = _dedupe_strings(paper.affiliations)
        merged_affiliations = _dedupe_strings(normalized_institutions + raw_affiliations)

        enriched.append(
            paper.with_institutions(
                raw_affiliations=raw_affiliations,
                normalized_institutions=normalized_institutions,
                merged_affiliations=merged_affiliations,
                institution_types=str(analysis.get("institution_types", "unknown") or "unknown"),
                institution_summary=str(analysis.get("institution_summary", "") or ""),
                institution_evidence_source=str(
                    analysis.get("evidence_source", "unknown") or "unknown"
                ),
            )
        )

    matched = sum(
        1 for paper in enriched if paper.institution_summary or paper.normalized_institutions
    )
    logger.info(
        "%s完成：%d/%d 篇成功补充机构摘要",
        stage_label, matched, len(enriched),
    )
    return enriched


def infer_paper_institutions(paper: Paper | RankedPaper) -> Optional[RankedPaper]:
    """对单篇论文执行机构归一分析（供测试脚本使用）。"""
    if paper is None:
        return None

    ranked = paper if isinstance(paper, RankedPaper) else RankedPaper.from_paper(paper)
    if not ranked.pdf_first_page_context:
        ranked = ranked.with_institutions(
            raw_affiliations=ranked.raw_affiliations,
            pdf_first_page_context=fetch_pdf_first_page_context(
                ranked.arxiv_id, pdf_url=ranked.pdf_url
            ),
        )

    enriched = _stage_infer_institutions([ranked], stage_label="单篇机构推断")
    return enriched[0] if enriched else ranked


def enrich_top_papers_with_institutions(
    ranked_papers: List[RankedPaper], top_k: int = 10
) -> List[RankedPaper]:
    """仅为最终 TOP K 论文补充机构信息，供日报展示。"""
    if not ranked_papers:
        return []

    top_slice = ranked_papers[:top_k]
    if not top_slice:
        return ranked_papers

    logger.info(
        "正在为 TOP %d 论文补充机构信息（PDF 首页推断）...", len(top_slice)
    )
    prepared: List[RankedPaper] = []
    for index, paper in enumerate(top_slice, 1):
        logger.info(
            "抽取第 %d/%d 篇 PDF 首页：%s",
            index, len(top_slice), paper.arxiv_id,
        )
        prepared.append(
            paper.with_institutions(
                raw_affiliations=paper.raw_affiliations,
                merged_affiliations=paper.affiliations,
                normalized_institutions=paper.normalized_institutions,
                institution_types=paper.institution_types,
                institution_summary=paper.institution_summary,
                institution_evidence_source=paper.institution_evidence_source,
                pdf_first_page_context=fetch_pdf_first_page_context(
                    paper.arxiv_id, pdf_url=paper.pdf_url
                ),
            )
        )

    enriched_top = _stage_infer_institutions(
        prepared, stage_label=f"TOP {len(top_slice)} 机构推断"
    )
    enriched_by_id = {paper.arxiv_id: paper for paper in enriched_top}

    merged: List[RankedPaper] = []
    for paper in ranked_papers:
        merged.append(enriched_by_id.get(paper.arxiv_id, paper))
    return merged


# ── 第二阶段：摘要精排 ─────────────────────────────────────────────────────────


def _normalize_ranked_papers(papers: List[RankedPaper]) -> List[RankedPaper]:
    """按 total_score 降序 + arxiv_id 次序重新排位。"""
    normalized: List[RankedPaper] = []
    for fallback_rank, paper in enumerate(papers, 1):
        if not paper.one_line_summary:
            paper = paper.with_scores(one_line_summary=_default_summary(paper))
        # 没打过分的 fallback_rank
        if paper.rank == 0:
            paper = paper.with_scores(rank=fallback_rank)
        normalized.append(paper)

    normalized.sort(
        key=lambda p: (p.total_score, str(p.arxiv_id).replace(".", "")),
        reverse=True,
    )
    for index, paper in enumerate(normalized, 1):
        normalized[index - 1] = paper.with_scores(rank=index)
    return normalized


def _stage2_rank(papers: List[Paper]) -> List[RankedPaper]:
    """对候选论文发送完整摘要，打分排出 TOP N。"""
    paper_blocks_list = []
    for i, paper in enumerate(papers, 1):
        paper_blocks_list.append(
            f"[{i}] ID:{paper.arxiv_id}\n"
            f"Title: {paper.title}\n"
            f"Authors: {fmt_authors(paper.authors)}\n"
            f"Abstract: {paper.abstract[:500]}\n"
        )

    prompt = prompts.render(
        "stage2_abstract_rank",
        topics_of_interest=TOPICS_OF_INTEREST,
        paper_blocks="\n".join(paper_blocks_list),
        total_score_max=TOTAL_SCORE_MAX,
        top_n=TOP_N,
    )


    try:
        logger.info(
            "阶段3/3 摘要精排：正在综合评估 %d 篇候选论文...", len(papers),
        )
        raw = chat(
            [{"role": "user", "content": prompt}],
            max_tokens=8000,
            label="stage2_abstract_rank",
        )
        data = extract_json(raw, list_roots=("top_papers",))
    except Exception as exc:
        logger.warning(
            "阶段3/3 摘要精排失败（%s），回退到候选前 %d 篇", exc, TOP_N,
        )
        return _normalize_ranked_papers(
            [RankedPaper.from_paper(p) for p in papers[:TOP_N]]
        )

    papers_by_id = {paper.arxiv_id: paper for paper in papers}
    result: List[RankedPaper] = []
    for meta in data.get("top_papers") or data.get("items") or []:
        if not isinstance(meta, dict):
            continue
        aid = str(meta.get("arxiv_id", ""))
        base = papers_by_id.get(aid)
        if base is None:
            continue
        result.append(
            RankedPaper.from_paper(base).with_scores(
                relevance_score=meta.get("relevance_score"),
                novelty_score=meta.get("novelty_score"),
                total_score=meta.get("total_score"),
                topic_category=meta.get("topic_category"),
                one_line_summary=meta.get("one_line_summary"),
                rank=meta.get("rank"),
            )
        )

    if not result:
        logger.warning("未匹配到论文 ID，回退到候选前 %d 篇", TOP_N)
        return _normalize_ranked_papers(
            [RankedPaper.from_paper(p) for p in papers[:TOP_N]]
        )

    logger.info(
        "阶段3/3 摘要精排完成：%d → TOP %d 篇", len(papers), len(result),
    )
    return _normalize_ranked_papers(result)


# ── 主入口 ────────────────────────────────────────────────────────────────────


def rank_papers(papers: List[Paper]) -> List[RankedPaper]:
    """两阶段排名：标题粗筛 → 摘要精排。"""
    if not papers:
        return []

    logger.info("输入 %d 篇论文，开始两阶段筛选...", len(papers))
    prefiltered = _rule_prefilter(papers)
    candidates = _stage1_filter(prefiltered)
    logger.info("进入摘要精排的候选数：%d 篇", len(candidates))
    return _stage2_rank(candidates)
