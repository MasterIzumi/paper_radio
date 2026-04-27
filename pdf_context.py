"""PDF 首页作者/机构上下文提取。"""
from __future__ import annotations

import logging
import re
from io import BytesIO
from typing import Iterable, List

from http_client import get_bytes

logger = logging.getLogger(__name__)

PDF_CONTEXT_MAX_CHARS = 8000
ARXIV_PDF = "https://arxiv.org/pdf/{arxiv_id}.pdf"

_NOISE_PATTERNS = [
    re.compile(r"^arXiv:\d{4}\.\d{4,5}", re.I),
    re.compile(r"^this work is licensed under", re.I),
    re.compile(r"^preprint\.? under review", re.I),
    re.compile(r"^accepted to", re.I),
    re.compile(r"^camera ready", re.I),
    re.compile(r"^page \d+ of \d+$", re.I),
    re.compile(r"^\d+\s*$"),
]
_SECTION_BREAK_PATTERN = re.compile(
    r"^(abstract|1\.?\s+introduction|introduction|contents?)\b",
    re.I,
)
_AFFILIATION_HINT_PATTERN = re.compile(
    r"\b("
    r"university|institute|college|school|academy|laboratory|lab\b|research|centre|center|"
    r"corporation|corp\.?|inc\.?|ltd\.?|company|technologies|technology|"
    r"google|meta|microsoft|nvidia|tesla|bytedance|huawei|xiaomi|amazon|apple|openai|"
    r"department|dept\.?|faculty|csail|ria|cmu|mit|stanford|tsinghua|berkeley|oxford|cambridge"
    r")\b",
    re.I,
)
_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_FOOTNOTE_MARKER_PATTERN = re.compile(r"^[\*\d†‡§¶]+[\)\].,:]?\s*")


def _clean_lines(text: str) -> List[str]:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return [line for line in lines if line]


def _is_noise_line(line: str) -> bool:
    if len(line) <= 1:
        return True
    return any(pattern.search(line) for pattern in _NOISE_PATTERNS)


def _dedupe_preserve_order(lines: Iterable[str]) -> List[str]:
    result: List[str] = []
    seen: set[str] = set()
    for line in lines:
        cleaned = line.strip()
        key = cleaned.casefold()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


def _looks_like_affiliation(line: str) -> bool:
    if _EMAIL_PATTERN.search(line):
        return True
    if _AFFILIATION_HINT_PATTERN.search(line):
        return True
    if "," in line and len(line.split()) <= 18:
        return True
    if _FOOTNOTE_MARKER_PATTERN.match(line) and len(line.split()) <= 20:
        return True
    return False


def _extract_title_block(lines: List[str]) -> List[str]:
    if not lines:
        return []
    collected: List[str] = []
    for index, line in enumerate(lines[:45]):
        if index >= 4 and _SECTION_BREAK_PATTERN.match(line):
            break
        collected.append(line)
    return collected[:24]


def _extract_bottom_block(lines: List[str], limit: int = 18) -> List[str]:
    if not lines:
        return []
    tail = [line for line in lines[-limit * 2 :] if not _is_noise_line(line)]
    return tail[-limit:]


def _extract_affiliation_candidates(lines: List[str]) -> List[str]:
    if not lines:
        return []
    candidates = [line for line in lines if _looks_like_affiliation(line)]
    ranked = sorted(
        candidates,
        key=lambda line: (
            _EMAIL_PATTERN.search(line) is None,
            _AFFILIATION_HINT_PATTERN.search(line) is None,
            len(line),
        ),
    )
    return ranked[:16]


def _render_section(title: str, lines: List[str]) -> str:
    deduped = _dedupe_preserve_order(lines)
    if not deduped:
        return f"[{title}]\nN/A"
    return f"[{title}]\n" + "\n".join(deduped)


def _extract_pdf_first_page_block(text: str) -> str:
    """从 PDF 首页抽机构相关的高价值上下文。

    相比直接把整页全文丢给 LLM，这里会优先保留：
    - 标题 / 作者块
    - 机构 / 邮箱 / 脚注候选
    - 页底候选文本
    并过滤一些 arXiv watermark、版权、页码类噪声。
    """
    if not text:
        return ""

    raw_lines = _clean_lines(text)
    lines = [line for line in raw_lines if not _is_noise_line(line)]
    if not lines:
        return ""

    title_block = _extract_title_block(lines)
    affiliation_candidates = _extract_affiliation_candidates(lines)
    bottom_block = _extract_bottom_block(lines)

    sections = [
        _render_section("Title and Author Block", title_block),
        _render_section("Affiliation Candidates", affiliation_candidates),
        _render_section("Bottom of First Page", bottom_block),
    ]
    joined = "\n\n".join(section.strip() for section in sections if section.strip()).strip()
    joined = re.sub(r"\n{3,}", "\n\n", joined)
    return joined[:PDF_CONTEXT_MAX_CHARS]


def fetch_pdf_first_page_context(arxiv_id: str, pdf_url: str = "") -> str:
    """下载 PDF 并提取第一页里和作者机构最相关的上下文。"""
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
