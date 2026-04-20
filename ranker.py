"""使用 LLM 对论文进行筛选与排序。"""
import json
import re
from typing import Dict, List

from config import MAX_PAPERS_TO_RANK, TOPICS_OF_INTEREST
from llm import chat
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


def _fmt_authors(paper: Dict) -> str:
    authors = paper.get("authors", [])
    if not authors:
        return "Unknown"
    base = ", ".join(authors[:4])
    return base + " et al." if len(authors) > 4 else base


def _fmt_affiliations(paper: Dict, max_affiliations: int = 6) -> str:
    affiliations = paper.get("affiliations", [])
    if not affiliations:
        return "N/A"

    deduped = []
    for affiliation in affiliations:
        cleaned = str(affiliation).strip()
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)

    base = "; ".join(deduped[:max_affiliations])
    return base + " ..." if len(deduped) > max_affiliations else base


def _dedupe_strings(values: List[str]) -> List[str]:
    deduped: List[str] = []
    for value in values:
        cleaned = str(value).strip()
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)
    return deduped


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
            # 退一步：尝试识别顶层 array 形式
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


def _safe_score(value, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _default_summary(paper: Dict) -> str:
    abstract = paper.get("abstract", "").strip()
    if abstract:
        first = re.split(r"(?<=[.!?。！？])\s+", abstract)[0].strip()
        if first:
            return first[:120]
    return paper.get("title", "N/A")


def _normalize_ranked_papers(papers: List[Dict]) -> List[Dict]:
    normalized = []
    for fallback_rank, paper in enumerate(papers, 1):
        rel = _safe_score(paper.get("relevance_score"))
        nov = _safe_score(paper.get("novelty_score"))
        total = paper.get("total_score")
        total = _safe_score(total, rel + nov)
        if total == 0 and any([rel, nov]):
            total = rel + nov

        normalized.append(
            {
                **paper,
                "relevance_score": rel,
                "novelty_score": nov,
                "total_score": total,
                "topic_category": paper.get("topic_category") or "未分类",
                "one_line_summary": paper.get("one_line_summary") or _default_summary(paper),
                "rank": _safe_score(paper.get("rank"), fallback_rank),
            }
        )

    normalized.sort(
        key=lambda paper: (
            _safe_score(paper.get("total_score")),
            str(paper.get("arxiv_id", "")).replace(".", ""),
        ),
        reverse=True,
    )
    for index, paper in enumerate(normalized, 1):
        paper["rank"] = index
    return normalized


def _rule_prefilter(papers: List[Dict]) -> List[Dict]:
    """先用本地规则预筛，减少全部标题直接送给 LLM。"""
    result = []
    for paper in papers[:MAX_PAPERS_TO_RANK]:
        text = " ".join(
            [
                paper.get("title", ""),
                paper.get("abstract", ""),
                " ".join(paper.get("categories", [])),
            ]
        ).lower()
        if any(keyword in text for keyword in PREFILTER_KEYWORDS):
            result.append(paper)

    if not result:
        fallback = papers[: min(STAGE1_KEEP * 2, len(papers))]
        print(f"  规则预筛未命中，回退保留前 {len(fallback)} 篇进入标题粗筛")
        return fallback

    print(f"  规则预筛：{min(len(papers), MAX_PAPERS_TO_RANK)} → {len(result)} 篇")
    return result


# ── 第一阶段：标题粗筛 ─────────────────────────────────────────────────────────

def _stage1_filter(papers: List[Dict]) -> List[Dict]:
    """
    仅发送标题，让 LLM 快速判断相关性，返回候选 ID 列表。
    输入可以很多，token 消耗极低。
    """
    title_lines = "\n".join(
        f"[{i}] {p.get('arxiv_id','')} | {p.get('title','')}"
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
        result = [p for p in papers if p.get("arxiv_id") in ids]
        print(f"  阶段1/3 标题粗筛完成：{len(papers)} → {len(result)} 篇候选")
        return result if result else papers[:STAGE1_KEEP]
    except Exception as e:
        print(f"  ⚠️  阶段1/3 标题粗筛失败（{e}），直接取前 {STAGE1_KEEP} 篇")
        return papers[:STAGE1_KEEP]


def _stage_infer_institutions(papers: List[Dict], stage_label: str = "机构推断") -> List[Dict]:
    """对给定论文集合执行 PDF 驱动的机构归一分析。"""
    if not papers:
        return []

    paper_blocks = []
    for index, paper in enumerate(papers, 1):
        pdf_context = (paper.get("pdf_first_page_context", "") or "").strip()
        paper_blocks.append(
            f"[{index}] ID:{paper.get('arxiv_id', '')}\n"
            f"Title: {paper.get('title', '')}\n"
            f"Authors: {_fmt_authors(paper)}\n"
            f"Raw Affiliations: {_fmt_affiliations(paper)}\n"
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
    except Exception as e:
        print(f"  ⚠️  {stage_label}失败（{e}），继续使用原始 affiliations")
        return papers

    analyses_by_id = {}
    for item in data.get("analyses", []):
        arxiv_id = item.get("arxiv_id", "")
        if arxiv_id:
            analyses_by_id[arxiv_id] = item

    enriched = []
    for paper in papers:
        analysis = analyses_by_id.get(paper.get("arxiv_id", ""))
        if not analysis:
            enriched.append(paper)
            continue

        normalized_institutions = analysis.get("normalized_institutions", [])
        if not isinstance(normalized_institutions, list):
            normalized_institutions = []
        normalized_institutions = _dedupe_strings(normalized_institutions)
        raw_affiliations = _dedupe_strings(paper.get("affiliations", []))
        merged_affiliations = _dedupe_strings(normalized_institutions + raw_affiliations)

        enriched.append(
            {
                **paper,
                "raw_affiliations": raw_affiliations,
                "affiliations": merged_affiliations,
                "normalized_institutions": normalized_institutions,
                "institution_types": analysis.get("institution_types", "unknown") or "unknown",
                "institution_summary": (analysis.get("institution_summary", "") or "").strip(),
                "institution_evidence_source": analysis.get("evidence_source", "unknown") or "unknown",
            }
        )

    matched = sum(1 for paper in enriched if paper.get("institution_summary") or paper.get("normalized_institutions"))
    print(f"  {stage_label}完成：{matched}/{len(enriched)} 篇成功补充机构摘要")
    return enriched


def infer_paper_institutions(paper: Dict) -> Dict:
    """对单篇论文执行机构归一分析，并回填元信息字段。"""
    if not paper:
        return {}
    if not paper.get("pdf_first_page_context"):
        paper = {
            **paper,
            "pdf_first_page_context": fetch_pdf_first_page_context(
                paper.get("arxiv_id", ""),
                pdf_url=paper.get("pdf_url", ""),
            ),
        }
    enriched = _stage_infer_institutions([paper], stage_label="单篇机构推断")
    return enriched[0] if enriched else paper


def enrich_top_papers_with_institutions(ranked_papers: List[Dict], top_k: int = 10) -> List[Dict]:
    """仅为最终 TOP K 论文补充机构信息，供日报展示。"""
    if not ranked_papers:
        return []

    top_slice = ranked_papers[:top_k]
    if not top_slice:
        return ranked_papers

    print(f"     正在为 TOP {len(top_slice)} 论文补充机构信息（PDF 首页推断）...")
    prepared: List[Dict] = []
    for index, paper in enumerate(top_slice, 1):
        print(f"       - 抽取第 {index}/{len(top_slice)} 篇 PDF 首页：{paper.get('arxiv_id', '')}")
        prepared.append(
            {
                **paper,
                "pdf_first_page_context": fetch_pdf_first_page_context(
                    paper.get("arxiv_id", ""),
                    pdf_url=paper.get("pdf_url", ""),
                ),
            }
        )

    enriched_top = _stage_infer_institutions(prepared, stage_label=f"TOP {len(top_slice)} 机构推断")
    enriched_by_id = {paper.get("arxiv_id"): paper for paper in enriched_top}
    merged: List[Dict] = []
    for paper in ranked_papers:
        merged.append(enriched_by_id.get(paper.get("arxiv_id"), paper))
    return merged


# ── 第二阶段：摘要精排 ─────────────────────────────────────────────────────────

def _stage2_rank(papers: List[Dict]) -> List[Dict]:
    """对候选论文发送完整摘要，打分排出 TOP 10。"""
    paper_blocks = []
    for i, p in enumerate(papers, 1):
        paper_blocks.append(
            f"[{i}] ID:{p.get('arxiv_id','')}\n"
            f"Title: {p.get('title','')}\n"
            f"Authors: {_fmt_authors(p)}\n"
            f"Abstract: {p.get('abstract','')[:500]}\n"
        )
    paper_list_text = "\n".join(paper_blocks)

    prompt = f"""你是 AI 与自动驾驶领域的顶级研究专家，请对以下候选论文进行精细排名。

## 关注的研究方向
{TOPICS_OF_INTEREST}

## 评分维度（各 0-10 分）
- **relevance_score**：与上述方向的相关程度
- **novelty_score**：方法新颖性与贡献潜力

## 候选论文
{paper_list_text}

## 输出要求
只返回 JSON，包含 top_papers 数组，每项字段：rank、arxiv_id、relevance_score、novelty_score、total_score、topic_category、one_line_summary（中文一句话总结）。不要任何解释文字，选出 TOP 10。"""

    try:
        print(f"  阶段3/3 摘要精排：正在综合评估 {len(papers)} 篇候选论文...")
        raw = chat([{"role": "user", "content": prompt}], max_tokens=8000)
        data = _extract_json(raw)
    except Exception as e:
        print(f"  ⚠️  阶段3/3 摘要精排失败（{e}），回退到候选前 10 篇")
        return _normalize_ranked_papers(papers[:10])

    papers_by_id = {p["arxiv_id"]: p for p in papers}
    result = []
    for meta in data.get("top_papers", []):
        aid = meta.get("arxiv_id", "")
        if aid in papers_by_id:
            result.append({**papers_by_id[aid], **meta})

    if not result:
        print("  ⚠️  未匹配到论文 ID，回退到候选前 10 篇")
        return _normalize_ranked_papers(papers[:10])

    print(f"  阶段3/3 摘要精排完成：{len(papers)} → TOP {len(result)} 篇")
    return _normalize_ranked_papers(result)


# ── 主入口 ────────────────────────────────────────────────────────────────────

def rank_papers(papers: List[Dict]) -> List[Dict]:
    """两阶段排名：标题粗筛 → 摘要精排。"""
    if not papers:
        return []

    print(f"  输入 {len(papers)} 篇论文，开始两阶段筛选...")
    prefiltered = _rule_prefilter(papers)
    candidates = _stage1_filter(prefiltered)
    print(f"  进入摘要精排的候选数：{len(candidates)} 篇")
    return _stage2_rank(candidates)
