"""从 arXiv HTML 版本抓取论文正文关键章节"""
from __future__ import annotations

import logging
import re
from typing import Optional

from bs4 import BeautifulSoup, Tag

from http_client import get_text

logger = logging.getLogger(__name__)

ARXIV_HTML = "https://arxiv.org/html/{arxiv_id}"

# 感兴趣的章节关键词（小写匹配）
TARGET_SECTIONS = [
    "introduction",
    "method", "methods", "methodology",
    "approach", "proposed",
    "model", "framework", "architecture",
    "overview",
]

# 跳过的章节（参考文献、附录等）
SKIP_SECTIONS = [
    "reference", "appendix", "acknowledgment", "acknowledgement",
    "conclusion", "related work", "experiment", "ablation",
    "limitation", "broader impact",
]

MAX_CHARS_PER_SECTION = 2000
MAX_TOTAL_CHARS = 6000


def _section_matches(heading: str, keywords: list) -> bool:
    h = heading.lower().strip()
    return any(kw in h for kw in keywords)


def fetch_sections(arxiv_id: str) -> Optional[str]:
    """
    抓取论文 HTML 版本，提取 Introduction + Method 章节文本。
    失败时返回 None（调用方降级到摘要）。
    """
    url = ARXIV_HTML.format(arxiv_id=arxiv_id)
    try:
        html = get_text(url)
    except RuntimeError as exc:
        logger.debug("fetch_sections %s HTML 抓取失败：%s", arxiv_id, exc)
        return None

    soup = BeautifulSoup(html, "html.parser")

    # arXiv HTML 用 <section> 包裹每个章节
    sections = soup.find_all("section")

    collected: list[str] = []
    total_chars = 0

    for sec in sections:
        if total_chars >= MAX_TOTAL_CHARS:
            break

        # 找章节标题
        heading_tag = sec.find(re.compile(r"^h[1-4]$"))
        if not heading_tag:
            continue
        heading_text = heading_tag.get_text(" ", strip=True)

        # 跳过不需要的章节
        if _section_matches(heading_text, SKIP_SECTIONS):
            continue
        if not _section_matches(heading_text, TARGET_SECTIONS):
            continue

        # 提取正文段落（去掉子 section 的内容避免重复）
        paragraphs = []
        for child in sec.children:
            if not isinstance(child, Tag):
                continue
            # 跳过嵌套 section（子章节）
            if child.name == "section":
                continue
            if child.name in ("p", "div"):
                text = child.get_text(" ", strip=True)
                if len(text) > 30:  # 过滤掉太短的碎片
                    paragraphs.append(text)

        if not paragraphs:
            continue

        section_text = f"### {heading_text}\n" + "\n".join(paragraphs)
        section_text = section_text[:MAX_CHARS_PER_SECTION]
        collected.append(section_text)
        total_chars += len(section_text)

    if not collected:
        return None

    return "\n\n".join(collected)
