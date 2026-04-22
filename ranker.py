"""使用 LLM 对论文进行筛选与排序。"""
from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

import prompts
from config import (
    BLACKLIST_KEYWORDS,
    BLACKLIST_SUBJECTS,
    INSTITUTION_INFERENCE_CONCURRENCY,
    MAX_PAPERS_TO_RANK,
    RAW_SCORE_MAX,
    TOPICS_OF_INTEREST,
)
from formatting import fmt_affiliations, fmt_authors
from llm import chat, extract_json
from models import Paper, RankedPaper
from pdf_context import fetch_pdf_first_page_context

logger = logging.getLogger(__name__)

# 第一阶段：仅凭标题快速过滤，保留候选数量
STAGE1_KEEP = 30
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


def _is_blacklisted_subject(paper: Paper, blacklist: set[str]) -> bool:
    """论文 categories 与 subject 黑名单有交集即剔除。比对大小写不敏感。"""
    if not blacklist:
        return False
    return any((cat or "").lower() in blacklist for cat in paper.categories)


def _build_blacklist_keyword_pattern(keyword: str) -> re.Pattern:
    """把一个黑名单关键词编成 word-boundary + 词间 ``\\s+`` + 可选复数 ``s?`` 的正则。

    - ``UAV`` → ``\\bUAVs?\\b``：命中 UAV / UAVs，但不误伤 UAVNet / UAV2
    - ``V2X`` → ``\\bV2Xs?\\b``：命中 V2X / V2X-based，但不误伤 V2XNet
    - ``Drone Racing`` → ``\\bDrone\\s+Racings?\\b``：允许词间多个空格
    """
    words = [w for w in keyword.split() if w]
    if not words:
        raise ValueError("empty blacklist keyword")
    core = r"\s+".join(re.escape(w) for w in words)
    return re.compile(rf"\b{core}s?\b", re.IGNORECASE)


_BLACKLIST_KEYWORD_PATTERNS: List[tuple[str, re.Pattern]] = [
    (kw, _build_blacklist_keyword_pattern(kw)) for kw in BLACKLIST_KEYWORDS if kw
]


def _is_blacklisted_keyword(paper: Paper) -> Optional[str]:
    """命中任一黑名单关键词即返回命中的关键词，否则返回 None。扫 title + abstract。"""
    if not _BLACKLIST_KEYWORD_PATTERNS:
        return None
    haystack_parts: List[str] = []
    if paper.title:
        haystack_parts.append(paper.title)
    if paper.abstract:
        haystack_parts.append(paper.abstract)
    if not haystack_parts:
        return None
    haystack = " \n ".join(haystack_parts)
    for keyword, pattern in _BLACKLIST_KEYWORD_PATTERNS:
        if pattern.search(haystack):
            return keyword
    return None


def _rule_prefilter(papers: List[Paper]) -> List[Paper]:
    """本地规则预筛全量候选——纯字符串匹配，零成本，不截断输入。

    三步：
    1. **subject 黑名单硬剔除**：论文任一 arXiv 分类落在 ``BLACKLIST_SUBJECTS``（如
       ``eess.SY`` / ``cs.MA``）即直接移除，不消耗后续 LLM 额度。
    2. **关键词白名单命中**：拼接 title + abstract + categories，任一
       ``PREFILTER_KEYWORDS`` 命中即保留（全军覆没时回退）。
    3. **关键词黑名单硬剔除**：扫 title + abstract，命中 ``BLACKLIST_KEYWORDS``
       （Drone Racing / V2V / V2X / UAV 等偏题主题）即剔除。

    LLM 输入上限 (MAX_PAPERS_TO_RANK) 在下一步 _stage1_filter 才生效。
    """
    blacklist = {s.lower() for s in BLACKLIST_SUBJECTS}

    after_subject_blacklist: List[Paper] = []
    subject_rejected = 0
    for paper in papers:
        if _is_blacklisted_subject(paper, blacklist):
            subject_rejected += 1
            continue
        after_subject_blacklist.append(paper)

    if subject_rejected:
        logger.info(
            "subject 黑名单剔除：%d 篇（命中 %s）",
            subject_rejected, ", ".join(sorted(BLACKLIST_SUBJECTS)),
        )

    keyword_matched: List[Paper] = []
    for paper in after_subject_blacklist:
        text = " ".join([paper.title, paper.abstract, " ".join(paper.categories)]).lower()
        if any(keyword in text for keyword in PREFILTER_KEYWORDS):
            keyword_matched.append(paper)

    if not keyword_matched:
        fallback = after_subject_blacklist[: min(STAGE1_KEEP * 2, len(after_subject_blacklist))]
        logger.info("关键词预筛未命中，回退保留前 %d 篇进入黑名单过滤 + 标题粗筛", len(fallback))
        keyword_matched = fallback

    result: List[Paper] = []
    kw_rejected = 0
    kw_rejected_by_keyword: Dict[str, int] = {}
    for paper in keyword_matched:
        hit = _is_blacklisted_keyword(paper)
        if hit:
            kw_rejected += 1
            kw_rejected_by_keyword[hit] = kw_rejected_by_keyword.get(hit, 0) + 1
            continue
        result.append(paper)

    if kw_rejected:
        breakdown = ", ".join(
            f"{kw}:{n}" for kw, n in sorted(kw_rejected_by_keyword.items(), key=lambda x: -x[1])
        )
        logger.info("关键词黑名单剔除：%d 篇（%s）", kw_rejected, breakdown)

    logger.info(
        "规则预筛：%d 输入 → subject 剔除 %d → 白名单命中 %d → 关键词黑名单剔除 %d → 剩 %d",
        len(papers), subject_rejected, len(keyword_matched), kw_rejected, len(result),
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
            tier="fast",
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


# ── 机构推断（PDF 首页 + LLM，每篇独立 + 并行）────────────────────────────────


def _build_institution_prompt(paper: RankedPaper) -> str:
    pdf_context = (paper.pdf_first_page_context or "").strip()
    return prompts.render(
        "institution_inference",
        topics_of_interest=TOPICS_OF_INTEREST,
        arxiv_id=paper.arxiv_id,
        title=paper.title,
        authors=fmt_authors(paper.authors),
        raw_affiliations=fmt_affiliations(
            paper, max_affiliations=6, prefer_normalized=False
        ),
        pdf_context=pdf_context or "N/A",
    )


def _apply_institution_analysis(
    paper: RankedPaper, analysis: Optional[Dict]
) -> RankedPaper:
    """把 LLM 返回的单篇分析结果合并回 RankedPaper。"""
    if not analysis:
        return paper

    normalized_list = analysis.get("normalized_institutions", [])
    if not isinstance(normalized_list, list):
        normalized_list = []
    normalized_institutions = _dedupe_strings(normalized_list)
    raw_affiliations = _dedupe_strings(paper.affiliations)
    merged_affiliations = _dedupe_strings(normalized_institutions + raw_affiliations)

    return paper.with_institutions(
        raw_affiliations=raw_affiliations,
        normalized_institutions=normalized_institutions,
        merged_affiliations=merged_affiliations,
        institution_types=str(analysis.get("institution_types", "unknown") or "unknown"),
        institution_summary=str(analysis.get("institution_summary", "") or ""),
        institution_evidence_source=str(
            analysis.get("evidence_source", "unknown") or "unknown"
        ),
    )


def _infer_one_paper_institution(
    paper: RankedPaper, *, fetch_pdf_if_missing: bool = True, label_suffix: str = ""
) -> RankedPaper:
    """单篇论文：抽 PDF 首页 → 调 LLM → 合并机构字段。失败时原样返回。"""
    pdf_context = (paper.pdf_first_page_context or "").strip()
    if not pdf_context and fetch_pdf_if_missing:
        try:
            pdf_context = fetch_pdf_first_page_context(
                paper.arxiv_id, pdf_url=paper.pdf_url
            )
        except Exception as exc:
            logger.warning(
                "PDF 首页抽取失败 %s：%s（继续仅靠 API affiliations 推断）",
                paper.arxiv_id, exc,
            )
            pdf_context = ""
        paper = paper.with_institutions(
            raw_affiliations=paper.raw_affiliations,
            normalized_institutions=paper.normalized_institutions,
            merged_affiliations=paper.affiliations,
            institution_types=paper.institution_types,
            institution_summary=paper.institution_summary,
            institution_evidence_source=paper.institution_evidence_source,
            pdf_first_page_context=pdf_context,
        )

    prompt = _build_institution_prompt(paper)
    try:
        raw = chat(
            [{"role": "user", "content": prompt}],
            # 单篇机构 JSON 其实只需要几百 tokens，给 3000 留 buffer：
            # 万一用户把 fast 档换成 reasoning 模型，不至于被思考过程吃光。
            max_tokens=3000,
            tier="fast",
            label=f"institution_inference{label_suffix}",
        )
        data = extract_json(raw)
    except Exception as exc:
        logger.warning(
            "机构推断失败 %s：%s，保留原始 affiliations", paper.arxiv_id, exc
        )
        return paper

    analysis = data if isinstance(data, dict) else None
    return _apply_institution_analysis(paper, analysis)


def infer_paper_institutions(paper: Paper | RankedPaper) -> Optional[RankedPaper]:
    """对单篇论文执行机构归一分析（供测试脚本使用）。"""
    if paper is None:
        return None

    ranked = paper if isinstance(paper, RankedPaper) else RankedPaper.from_paper(paper)
    return _infer_one_paper_institution(ranked, label_suffix=":single")


def enrich_papers_with_institutions(
    papers: List[RankedPaper],
) -> List[RankedPaper]:
    """对给定的一组论文并行补充机构信息。

    每篇论文一个 worker：``fetch PDF 首页 → 调 LLM 推断``。同一个 ThreadPoolExecutor
    上限既限制 arxiv PDF 并发，也限制 LLM 调用并发；单篇失败不影响其它论文。

    调用方决定要机构化哪些论文；在当前 pipeline 中通常是"stage1 通过的全部候选集"。
    """
    if not papers:
        return []

    workers = max(1, min(INSTITUTION_INFERENCE_CONCURRENCY, len(papers)))
    logger.info(
        "正在为 %d 篇候选并行补充机构信息（并发 %d）...",
        len(papers), workers,
    )

    enriched_by_id: Dict[str, RankedPaper] = {}
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="inst-infer") as pool:
        futures = {
            pool.submit(
                _infer_one_paper_institution,
                paper,
                label_suffix=f":cand{index}",
            ): paper
            for index, paper in enumerate(papers, 1)
        }
        completed = 0
        for future in as_completed(futures):
            original = futures[future]
            completed += 1
            try:
                result = future.result()
            except Exception as exc:
                logger.warning(
                    "机构推断 worker 异常 %s：%s，保留原始 affiliations",
                    original.arxiv_id, exc,
                )
                result = original
            enriched_by_id[original.arxiv_id] = result
            status = "✓" if (result.institution_summary or result.normalized_institutions) else "·"
            logger.info(
                "[%d/%d] %s 机构推断完成 %s",
                completed, len(papers), status, original.arxiv_id,
            )

    matched = sum(
        1 for paper in enriched_by_id.values()
        if paper.institution_summary or paper.normalized_institutions
    )
    logger.info(
        "机构推断结束：%d/%d 篇拿到机构摘要", matched, len(papers),
    )

    # 按原顺序返回（ThreadPoolExecutor 的 as_completed 会打乱顺序）
    return [enriched_by_id.get(paper.arxiv_id, paper) for paper in papers]


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


def _as_ranked(paper: Paper | RankedPaper) -> RankedPaper:
    """把 Paper 提升成 RankedPaper（已经是 RankedPaper 的原样返回）。"""
    return paper if isinstance(paper, RankedPaper) else RankedPaper.from_paper(paper)


def _stage2_rank(papers: List[RankedPaper]) -> List[RankedPaper]:
    """对候选论文发送摘要，**对全量逐篇打分**，返回完整排序后的列表。

    这里不再截断 TOP N——下游 reporter 按阈值 + 最小数动态选取要展示的论文。
    """
    if not papers:
        return []

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
        raw_score_max=RAW_SCORE_MAX,
        paper_count=len(papers),
    )

    try:
        logger.info(
            "摘要精排：正在对 %d 篇候选逐篇打分...", len(papers),
        )
        raw = chat(
            [{"role": "user", "content": prompt}],
            # strong 档常是 reasoning 模型（kimi-k2.5 / claude opus thinking），
            # 思考链也占 max_tokens 预算；全量打分的 JSON 比旧 TOP 10 大一些，给
            # 24000 留足推理余量，避免截断后输出半截 JSON 解析失败。
            max_tokens=24000,
            tier="strong",
            label="stage2_abstract_rank",
        )
        data = extract_json(raw, list_roots=("ranked_papers",))
    except Exception as exc:
        logger.warning(
            "摘要精排失败（%s），回退到 0 分兜底（让所有候选都出现在 selected 快照里）",
            exc,
        )
        return _normalize_ranked_papers(list(papers))

    papers_by_id = {paper.arxiv_id: paper for paper in papers}
    scored_ids: set[str] = set()
    result: List[RankedPaper] = []
    for meta in data.get("ranked_papers") or data.get("items") or []:
        if not isinstance(meta, dict):
            continue
        aid = str(meta.get("arxiv_id", ""))
        base = papers_by_id.get(aid)
        if base is None:
            continue
        scored_ids.add(aid)
        result.append(
            base.with_scores(
                relevance_score=meta.get("relevance_score"),
                novelty_score=meta.get("novelty_score"),
                total_score=meta.get("total_score"),
                topic_category=meta.get("topic_category"),
                one_line_summary=meta.get("one_line_summary"),
                rank=meta.get("rank"),
            )
        )

    # LLM 漏评的候选用 0 分兜底塞进去，保证 selected_papers 快照完整
    missing = [paper for paper in papers if paper.arxiv_id not in scored_ids]
    if missing:
        logger.warning(
            "摘要精排 LLM 漏了 %d/%d 篇，按 0 分兜底补入：%s",
            len(missing), len(papers),
            ", ".join(p.arxiv_id for p in missing[:5]) + ("..." if len(missing) > 5 else ""),
        )
        result.extend(missing)

    logger.info(
        "摘要精排完成：%d 篇候选中 %d 篇拿到评分，%d 篇兜底 0 分",
        len(papers), len(scored_ids), len(missing),
    )
    return _normalize_ranked_papers(result)


# ── 公开主入口 ────────────────────────────────────────────────────────────────


def run_stage1_filter(papers: List[Paper]) -> List[RankedPaper]:
    """规则预筛 + LLM 标题粗筛，返回即将进入机构推理 / 摘要精排的候选集。

    返回的是 ``RankedPaper`` 列表（分数还是 0），下游直接在同一对象上累加机构 /
    评分 / 加分扣分字段。
    """
    if not papers:
        return []

    logger.info("输入 %d 篇论文，开始粗筛...", len(papers))
    prefiltered = _rule_prefilter(papers)
    candidates = _stage1_filter(prefiltered)
    logger.info("进入候选集的论文数：%d 篇", len(candidates))
    return [_as_ranked(p) for p in candidates]


def run_stage2_rank(papers: List[RankedPaper]) -> List[RankedPaper]:
    """摘要精排：对候选集（通常已补机构）逐篇打分，返回完整排序列表。"""
    return _stage2_rank(papers)
