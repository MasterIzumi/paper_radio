"""PDF 首页作者/机构上下文提取。"""
from __future__ import annotations

import logging
import re
from io import BytesIO

from http_client import get_bytes

logger = logging.getLogger(__name__)

PDF_CONTEXT_MAX_CHARS = 8000
ARXIV_PDF = "https://arxiv.org/pdf/{arxiv_id}.pdf"


def _clean_lines(text: str) -> list[str]:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return [line for line in lines if line]


def _extract_pdf_first_page_block(text: str) -> str:
    """返回整页文本（行级去多余空白、连续空行压缩、字符数封顶）。

    之前只保留头 40 行 + 尾 20 行，容易丢掉中部 footnote / affiliation 标注
    （比如两列排版里机构写在作者块和正文之间，或者被 pypdf 切成很多短行）。
    现在保留全页，靠 LLM 自己挑重要片段，只做体积裁剪。
    """
    if not text:
        return ""

    lines = _clean_lines(text)
    if not lines:
        return ""

    joined = "\n".join(lines)
    joined = re.sub(r"\n{3,}", "\n\n", joined).strip()
    return joined[:PDF_CONTEXT_MAX_CHARS]


def fetch_pdf_first_page_context(arxiv_id: str, pdf_url: str = "") -> str:
    """下载 PDF 并提取第一页较大范围文本，兼顾标题区与页底脚注候选。"""
    from pypdf import PdfReader

    target_url = pdf_url or ARXIV_PDF.format(arxiv_id=arxiv_id)
    try:
        content = get_bytes(target_url)
    except RuntimeError as exc:
        logger.debug("PDF 下载失败 %s：%s", target_url, exc)
        return ""

    try:
        reader = PdfReader(BytesIO(content))
        if not reader.pages:
            return ""
        first_page_text = reader.pages[0].extract_text() or ""
    except Exception as exc:
        logger.debug("PDF 解析失败 %s：%s", target_url, exc)
        return ""

    return _extract_pdf_first_page_block(first_page_text)
