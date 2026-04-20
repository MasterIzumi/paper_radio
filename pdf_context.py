"""PDF 首页作者/机构上下文提取。"""
from __future__ import annotations

import logging
import re
from io import BytesIO

from http_client import get_bytes

logger = logging.getLogger(__name__)

PDF_CONTEXT_MAX_CHARS = 5000
ARXIV_PDF = "https://arxiv.org/pdf/{arxiv_id}.pdf"


def _clean_lines(text: str) -> list[str]:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return [line for line in lines if line]


def _extract_pdf_first_page_block(text: str) -> str:
    if not text:
        return ""

    lines = _clean_lines(text)
    if not lines:
        return ""

    top_lines = lines[:40]
    bottom_lines = lines[-20:] if len(lines) > 20 else []

    merged_lines: list[str] = []
    for line in top_lines + bottom_lines:
        if line not in merged_lines:
            merged_lines.append(line)

    joined = "\n".join(merged_lines)
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
