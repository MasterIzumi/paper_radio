"""使用 LLM 对论文进行筛选与排序。"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

from config import MAX_PAPERS_TO_RANK, TOPICS_OF_INTEREST
from formatting import fmt_affiliations, fmt_authors
from llm import chat
from models import Paper, RankedPaper
from pdf_context import fetch_pdf_first_page_context

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


def _extract_json(text: str) -> dict:
    """尽力从 LLM 输出中抠出 JSON 对象。

    策略：
    1. 先剥掉 ``` / ```json 等 code fence，尝试直接 ``json.loads``。
    2. 如果顶层是 array，则包装成 ``{"items": [...]}``，方便调用方统一访问。
    3. 否则回退到“找首个 { 到末尾 }”的宽松抠取。
    """
    if not text:
        raise ValueError("空响应")

    cleaned = re.sub(r"```(?:json)?\s*", "", text).replace("```", "").strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        data = None

    if data is None:
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start == -1 or end == 0:
            arr_start = cleaned.find("[")
            arr_end = cleaned.rfind("]") + 1
            if arr_start != -1 and arr_end > arr_start:
                try:
                    arr = json.loads(cleaned[arr_start:arr_end])
                except json.JSONDecodeError as exc:
                    raise ValueError(f"无法解析 JSON：{exc}") from exc
                return {"items": arr} if isinstance(arr, list) else {}
            raise ValueError("找不到 JSON 对象")
        try:
            data = json.loads(cleaned[start:end])
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON 解析失败：{exc}") from exc

    if isinstance(data, list):
        return {"items": data}
    if not isinstance(data, dict):
        raise ValueError(f"期望 JSON object，实际得到 {type(data).__name__}")
    return data


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
        print(f"  规则预筛未命中，回退保留前 {len(fallback)} 篇进入标题粗筛")
        return fallback

    print(f"  规则预筛：{min(len(papers), MAX_PAPERS_TO_RANK)} → {len(result)} 篇")
    return result


# ── 第一阶段：标题粗筛 ─────────────────────────────────────────────────────────


def _stage1_filter(papers: List[Paper]) -> List[Paper]:
    """仅发送标题，让 LLM 快速判断相关性，返回候选列表。"""
    title_lines = "\n".join(
        f"[{i}] {p.arxiv_id} | {p.title}"
        for i, p in enumerate(papers[:MAX_PAPERS_TO_RANK], 1)
    )

    prompt = f"""你是 AI 与自动驾驶领域专家。以下是 arXiv 最新论文标题列表，请快速筛选出与以下方向相关的论文：

{TOPICS_OF_INTEREST}

## 论文标题列表
{title_lines}

    ## 输出要求
只返回 JSON，格式为 relevant_ids 字段包含相关论文 arxiv_id 的数组，不要任何解释文字。
宁可多选，不要漏掉相关论文，约选 {STAGE1_KEEP} 篇。"""

    try:
        print(f"  阶段1/3 标题粗筛：向 LLM 发送 {len(papers)} 篇标题...")
        raw = chat([{"role": "user", "content": prompt}], max_tokens=16000)
        data = _extract_json(raw)
        ids = set(data.get("relevant_ids", []))
        result = [p for p in papers if p.arxiv_id in ids]
        print(f"  阶段1/3 标题粗筛完成：{len(papers)} → {len(result)} 篇候选")
        return result if result else papers[:STAGE1_KEEP]
    except Exception as exc:
        print(f"  ⚠️  阶段1/3 标题粗筛失败（{exc}），直接取前 {STAGE1_KEEP} 篇")
        return papers[:STAGE1_KEEP]


# ── 机构推断（PDF 首页 + LLM）────────────────────────────────────────────────


def _stage_infer_institutions(
    papers: List[RankedPaper], stage_label: str = "机构推断"
) -> List[RankedPaper]:
    """对给定论文集合执行 PDF 驱动的机构归一分析。"""
    if not papers:
        return []

    paper_blocks = []
    for index, paper in enumerate(papers, 1):
        pdf_context = (paper.pdf_first_page_context or "").strip()
        paper_blocks.append(
            f"[{index}] ID:{paper.arxiv_id}\n"
            f"Title: {paper.title}\n"
            f"Authors: {fmt_authors(paper.authors)}\n"
            f"Raw Affiliations: {fmt_affiliations(paper, max_affiliations=6, prefer_normalized=False)}\n"
            f"PDF First Page Context: {pdf_context or 'N/A'}\n"
        )

    prompt = f"""你是学术机构识别助手。请根据下面每篇论文的作者和 arXiv API 提供的原始 affiliations，
以及补充提供的 PDF 首页文本，将机构信息归一到“学校 / 公司 / 研究机构”名称层级，供后续论文打分使用。

## 任务要求
1. 只能基于输入中给出的 Raw Affiliations、PDF First Page Context 做归纳，不要臆造未提供的机构。
2. 机构粒度到学校、公司、研究机构名称即可，不要保留学院、系、实验室层级。
3. 如果原始 affiliations 太少或没有，明确写 unknown。
4. 输出字段：
   - arxiv_id
   - normalized_institutions: 机构名称数组，尽量去重、规范化
   - institution_types: 从 university / company / research_lab / mixed / unknown 中选择一个最合适的标签
   - institution_summary: 一句中文简述，概括这篇论文的机构背景
   - evidence_source: 从 api / pdf / api+pdf / unknown 中选择，表示本次判断主要依据

## 关注方向
{TOPICS_OF_INTEREST}

## 候选论文
{chr(10).join(paper_blocks)}

## 输出要求
只返回 JSON，格式为 analyses 数组，不要任何解释文字。"""

    try:
        print(f"  {stage_label}：正在归一 {len(papers)} 篇论文的机构信息...")
        raw = chat([{"role": "user", "content": prompt}], max_tokens=8000)
        data = _extract_json(raw)
    except Exception as exc:
        print(f"  ⚠️  {stage_label}失败（{exc}），继续使用原始 affiliations")
        return papers

    analyses_by_id: Dict[str, Dict] = {}
    for item in data.get("analyses", []) or data.get("items", []):
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
    print(f"  {stage_label}完成：{matched}/{len(enriched)} 篇成功补充机构摘要")
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

    print(f"     正在为 TOP {len(top_slice)} 论文补充机构信息（PDF 首页推断）...")
    prepared: List[RankedPaper] = []
    for index, paper in enumerate(top_slice, 1):
        print(f"       - 抽取第 {index}/{len(top_slice)} 篇 PDF 首页：{paper.arxiv_id}")
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
    """对候选论文发送完整摘要，打分排出 TOP 10。"""
    paper_blocks = []
    for i, paper in enumerate(papers, 1):
        paper_blocks.append(
            f"[{i}] ID:{paper.arxiv_id}\n"
            f"Title: {paper.title}\n"
            f"Authors: {fmt_authors(paper.authors)}\n"
            f"Abstract: {paper.abstract[:500]}\n"
        )
    paper_list_text = "\n".join(paper_blocks)

    prompt = f"""你是 AI 与自动驾驶领域的顶级研究专家，请对以下候选论文进行精细排名。

## 关注的研究方向
{TOPICS_OF_INTEREST}

## 评分维度（各 0-10 分）
- **relevance_score**：与上述方向的相关程度
- **novelty_score**：方法新颖性与贡献潜力
- **total_score**：上述两个维度之和（0-20），作为最终排序依据

## 候选论文
{paper_list_text}

## 输出要求
只返回 JSON，包含 top_papers 数组，每项字段：rank、arxiv_id、relevance_score（0-10）、novelty_score（0-10）、total_score（relevance_score + novelty_score，0-20）、topic_category、one_line_summary（中文一句话总结）。不要任何解释文字，选出 TOP 10。"""

    try:
        print(f"  阶段3/3 摘要精排：正在综合评估 {len(papers)} 篇候选论文...")
        raw = chat([{"role": "user", "content": prompt}], max_tokens=8000)
        data = _extract_json(raw)
    except Exception as exc:
        print(f"  ⚠️  阶段3/3 摘要精排失败（{exc}），回退到候选前 10 篇")
        return _normalize_ranked_papers([RankedPaper.from_paper(p) for p in papers[:10]])

    papers_by_id = {paper.arxiv_id: paper for paper in papers}
    result: List[RankedPaper] = []
    for meta in data.get("top_papers", []) or data.get("items", []):
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
        print("  ⚠️  未匹配到论文 ID，回退到候选前 10 篇")
        return _normalize_ranked_papers([RankedPaper.from_paper(p) for p in papers[:10]])

    print(f"  阶段3/3 摘要精排完成：{len(papers)} → TOP {len(result)} 篇")
    return _normalize_ranked_papers(result)


# ── 主入口 ────────────────────────────────────────────────────────────────────


def rank_papers(papers: List[Paper]) -> List[RankedPaper]:
    """两阶段排名：标题粗筛 → 摘要精排。"""
    if not papers:
        return []

    print(f"  输入 {len(papers)} 篇论文，开始两阶段筛选...")
    prefiltered = _rule_prefilter(papers)
    candidates = _stage1_filter(prefiltered)
    print(f"  进入摘要精排的候选数：{len(candidates)} 篇")
    return _stage2_rank(candidates)
