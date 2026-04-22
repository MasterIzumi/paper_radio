"""生成每日 Markdown 报告"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List

import prompts
from config import (
    DEEP_ANALYSIS_MAX_PAPERS,
    DEEP_ANALYSIS_MIN_TOTAL_SCORE,
    LLM_PROVIDER,
    TOTAL_SCORE_MAX,
)
from formatting import escape_md_cell, fmt_affiliations, fmt_authors
from fulltext import fetch_sections
from llm import chat, get_active_model
from models import RankedPaper

logger = logging.getLogger(__name__)


def _select_deep_analysis_papers(ranked_papers: List[RankedPaper]) -> List[RankedPaper]:
    eligible = [
        paper for paper in ranked_papers if paper.total_score >= DEEP_ANALYSIS_MIN_TOTAL_SCORE
    ]
    return eligible[:DEEP_ANALYSIS_MAX_PAPERS]


def _deep_analysis(paper: RankedPaper) -> str:
    """为单篇论文生成深度分析，优先使用正文，降级到摘要。"""
    fulltext = fetch_sections(paper.arxiv_id)
    if fulltext:
        content_label = "正文节选（Introduction / Method）"
        content_body = fulltext
    else:
        content_label = "摘要（未找到 HTML 全文）"
        content_body = paper.abstract

    prompt = prompts.render(
        "deep_analysis",
        title=paper.title,
        authors=fmt_authors(paper.authors),
        affiliations=fmt_affiliations(paper),
        topic_category=paper.topic_category,
        content_label=content_label,
        content_body=content_body,
    )

    use_thinking = LLM_PROVIDER == "anthropic"
    return chat(
        [{"role": "user", "content": prompt}],
        # 三段 Markdown 输出实际只有 ~1500 tokens，给 16000 主要为 reasoning 模型
        # 的思考链预留空间（thinking 模式下 anthropic / kimi 都会额外消耗）。
        max_tokens=16000,
        thinking=use_thinking,
        tier="strong",
        label="deep_analysis",
    ).strip()


def generate_report(ranked_papers: List[RankedPaper]) -> str:
    """生成完整的每日 Markdown 报告。"""
    today_str = datetime.now().strftime("%Y年%m月%d日")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines: List[str] = []

    fast_model = get_active_model("fast")
    strong_model = get_active_model("strong")

    lines += [
        f"# 📡 每日论文摘要 | {today_str}",
        "",
        "> **关注领域**：端到端自动驾驶 · 世界模型 · VLA 模型 · 空间智能 · 自动驾驶大模型",
        f"> **精选论文**：{len(ranked_papers)} 篇 | 来源：arXiv cs.CV / cs.RO",
        f"> **模型**：粗筛/机构 `{fast_model}` · 精排/精读 `{strong_model}`",
        "",
        "---",
        "",
    ]

    if not ranked_papers:
        lines.append("今日暂无符合条件的论文，请明日再试。\n")
        return "\n".join(lines)

    # ── TOP 10 速览表格 ───────────────────────────────────────────────────────
    lines += [
        "## 🏆 TOP 10 论文速览",
        "",
        "| # | 标题 | 机构 | 方向 | 综合分 | 一句话总结 |",
        "|---|------|------|------|--------|-----------|",
    ]
    for paper in ranked_papers[:10]:
        title = escape_md_cell(paper.title or "N/A")
        url = paper.primary_url
        affs = escape_md_cell(fmt_affiliations(paper))
        topic = escape_md_cell(paper.topic_category or "—")
        score = escape_md_cell(paper.total_score)
        summary = escape_md_cell(paper.one_line_summary or "—")
        rank = escape_md_cell(paper.rank or "—")
        lines.append(
            f"| {rank} | [{title}]({url}) | {affs} | {topic} | {score}/{TOTAL_SCORE_MAX} | {summary} |"
        )

    lines += ["", "---", ""]

    # ── TOP 10 详细卡片 ───────────────────────────────────────────────────────
    lines += ["## 📋 TOP 10 论文列表", ""]
    for i, paper in enumerate(ranked_papers[:10], 1):
        lines += [
            f"### {i}. {paper.title or 'N/A'}",
            "",
            f"- **arXiv**: [{paper.arxiv_id}]({paper.primary_url})",
            f"- **作者**: {fmt_authors(paper.authors)}",
            f"- **机构**: {fmt_affiliations(paper)}",
            f"- **方向**: {paper.topic_category or '—'} | **提交**: {paper.published_day or 'N/A'}",
            f"- **评分**: 相关性 {paper.relevance_score} · 新颖性 {paper.novelty_score}",
            f"- **摘要**: {paper.one_line_summary or '—'}",
            "",
        ]

    lines += ["---", ""]

    deep_analysis_papers = _select_deep_analysis_papers(ranked_papers)

    # ── 深度简报 ──────────────────────────────────────────────────────────────
    lines += [
        "## 🔬 深度简报",
        "",
        (
            f"*以下最多分析 {DEEP_ANALYSIS_MAX_PAPERS} 篇，"
            f"仅纳入总分 >= {DEEP_ANALYSIS_MIN_TOTAL_SCORE} 的论文；"
            f"由 `{strong_model}` 基于摘要或正文节选生成*"
        ),
        "",
    ]

    if not deep_analysis_papers:
        lines += ["今日没有达到精读阈值的论文，因此不生成深度分析。", ""]

    for i, paper in enumerate(deep_analysis_papers, 1):
        title = paper.title or "N/A"
        url = paper.primary_url

        logger.info("生成第 %d 篇深度分析：%s", i, title[:60])
        analysis = _deep_analysis(paper)

        lines += [
            f"### 🥇 #{i} | [{title}]({url})",
            "",
            "| | |",
            "|---|---|",
            f"| **arXiv** | [{paper.arxiv_id}]({url}) |",
            f"| **作者** | {fmt_authors(paper.authors)} |",
            f"| **方向** | {paper.topic_category or '—'} |",
            f"| **提交** | {paper.published_day or 'N/A'} |",
            "",
            analysis,
            "",
            "---",
            "",
        ]

    lines += [f"*本报告由 `{strong_model}` 自动生成 · {now_str}*"]
    return "\n".join(lines)
