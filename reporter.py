"""生成每日 Markdown 报告"""
from datetime import datetime
from typing import Dict, List

from config import (
    DEEP_ANALYSIS_MAX_PAPERS,
    DEEP_ANALYSIS_MIN_TOTAL_SCORE,
    LLM_PROVIDER,
)
from fulltext import fetch_sections
from llm import chat
from recent_report import escape_md_cell


def _fmt_authors(paper: Dict) -> str:
    authors = paper.get("authors", [])
    if not authors:
        return "Unknown"
    base = ", ".join(authors[:4])
    return base + " et al." if len(authors) > 4 else base


def _fmt_affiliations(paper: Dict) -> str:
    normalized = paper.get("normalized_institutions", [])
    if normalized:
        base = "; ".join(str(item).strip() for item in normalized[:3] if str(item).strip())
        if len(normalized) > 3:
            return base + " ..."
        if base:
            return base

    affiliations = paper.get("affiliations", [])
    if not affiliations:
        return "N/A"

    deduped = []
    for affiliation in affiliations:
        if affiliation and affiliation not in deduped:
            deduped.append(affiliation)

    base = "; ".join(deduped[:3])
    return base + " ..." if len(deduped) > 3 else base


def _pub_date(paper: Dict) -> str:
    pub = paper.get("published", "")
    return pub[:10] if pub else "N/A"


def _score_value(paper: Dict, field: str) -> int:
    value = paper.get(field, 0)
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return 0


def _select_deep_analysis_papers(ranked_papers: List[Dict]) -> List[Dict]:
    eligible = [
        paper for paper in ranked_papers
        if _score_value(paper, "total_score") >= DEEP_ANALYSIS_MIN_TOTAL_SCORE
    ]
    return eligible[:DEEP_ANALYSIS_MAX_PAPERS]


def _deep_analysis(paper: Dict) -> str:
    """为单篇论文生成深度分析，优先使用正文，降级到摘要。"""
    arxiv_id = paper.get("arxiv_id", "")

    # 尝试抓正文
    fulltext = fetch_sections(arxiv_id)
    if fulltext:
        content_label = "正文节选（Introduction / Method）"
        content_body = fulltext
    else:
        content_label = "摘要（未找到 HTML 全文）"
        content_body = paper.get("abstract", "")

    prompt = f"""你是 AI 领域的资深研究员，以犀利的学术眼光著称。请深度分析以下论文。

**标题**: {paper.get('title', '')}
**作者**: {_fmt_authors(paper)}
**机构**: {_fmt_affiliations(paper)}
**方向**: {paper.get('topic_category', '')}
**{content_label}**:
{content_body}

请用中文输出以下三部分（直接输出 Markdown，不加额外标题层级）：

#### 方法介绍
（3-4 句）清晰介绍核心方法和技术创新点，需提及具体的模块/架构设计。

#### 贡献锐评
（2-3 句）批判性评价其 contribution——指出真正的技术亮点，同时不留情面地点出潜在局限、实验不足或过度夸大之处。

#### 影响力预测
（1 句）判断该工作对领域的潜在影响力与实际价值。"""

    use_thinking = (LLM_PROVIDER == "anthropic")
    return chat(
        [{"role": "user", "content": prompt}],
        max_tokens=6000,
        thinking=use_thinking,
    ).strip()


def generate_report(ranked_papers: List[Dict]) -> str:
    """生成完整的每日 Markdown 报告。"""
    today_str = datetime.now().strftime("%Y年%m月%d日")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines: List[str] = []

    # 用哪个模型
    from llm import _get_settings
    _, _, _, active_model = _get_settings()

    lines += [
        f"# 📡 每日论文摘要 | {today_str}",
        "",
        "> **关注领域**：端到端自动驾驶 · 世界模型 · VLA 模型 · 空间智能 · 自动驾驶大模型",
        f"> **精选论文**：{len(ranked_papers)} 篇 | 来源：arXiv cs.CV / cs.RO",
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
    for p in ranked_papers[:10]:
        title   = escape_md_cell(p.get("title", "N/A"))
        url     = p.get("abs_url") or f"https://arxiv.org/abs/{p.get('arxiv_id','')}"
        affs    = escape_md_cell(_fmt_affiliations(p))
        topic   = escape_md_cell(p.get("topic_category", "—"))
        score   = escape_md_cell(p.get("total_score", "—"))
        summary = escape_md_cell(p.get("one_line_summary", "—"))
        rank    = escape_md_cell(p.get("rank", "—"))
        lines.append(f"| {rank} | [{title}]({url}) | {affs} | {topic} | {score}/30 | {summary} |")

    lines += ["", "---", ""]

    # ── TOP 10 详细卡片 ───────────────────────────────────────────────────────
    lines += ["## 📋 TOP 10 论文列表", ""]
    for i, p in enumerate(ranked_papers[:10], 1):
        title   = p.get("title", "N/A")
        url     = p.get("abs_url") or f"https://arxiv.org/abs/{p.get('arxiv_id','')}"
        aid     = p.get("arxiv_id", "")
        authors = _fmt_authors(p)
        topic   = p.get("topic_category", "—")
        pub     = _pub_date(p)
        rel     = p.get("relevance_score", "—")
        nov     = p.get("novelty_score", "—")
        summary = p.get("one_line_summary", "—")

        lines += [
            f"### {i}. {title}",
            "",
            f"- **arXiv**: [{aid}]({url})",
            f"- **作者**: {authors}",
            f"- **机构**: {_fmt_affiliations(p)}",
            f"- **方向**: {topic} | **提交**: {pub}",
            f"- **评分**: 相关性 {rel} · 新颖性 {nov}",
            f"- **摘要**: {summary}",
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
            f"由 `{active_model}` 基于摘要或正文节选生成*"
        ),
        "",
    ]

    if not deep_analysis_papers:
        lines += [
            "今日没有达到精读阈值的论文，因此不生成深度分析。",
            "",
        ]

    for i, paper in enumerate(deep_analysis_papers, 1):
        title   = paper.get("title", "N/A")
        url     = paper.get("abs_url") or f"https://arxiv.org/abs/{paper.get('arxiv_id','')}"
        aid     = paper.get("arxiv_id", "")
        authors = _fmt_authors(paper)
        topic   = paper.get("topic_category", "—")
        pub     = _pub_date(paper)

        print(f"  → 生成第 {i} 篇深度分析：{title[:60]}...")
        analysis = _deep_analysis(paper)

        lines += [
            f"### 🥇 #{i} | [{title}]({url})",
            "",
            "| | |",
            "|---|---|",
            f"| **arXiv** | [{aid}]({url}) |",
            f"| **作者** | {authors} |",
            f"| **方向** | {topic} |",
            f"| **提交** | {pub} |",
            "",
            analysis,
            "",
            "---",
            "",
        ]

    lines += [f"*本报告由 `{active_model}` 自动生成 · {now_str}*"]
    return "\n".join(lines)
