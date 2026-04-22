"""arXiv 论文抓取模块。

默认策略：
1. 优先抓取 arXiv recent 页面，按日期段获取最近 N 天论文
2. 测试脚本直接使用页面抓取结果
3. 主流程可在页面抓取后，再用 arXiv API 按 id_list 补全摘要、作者、机构等元数据
"""
from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup, Tag

from config import (
    ARXIV_MAX_RESULTS,
    DAYS_BACK,
    FETCH_CATEGORIES,
)
from http_client import get_bytes, get_text
from models import Paper

logger = logging.getLogger(__name__)

ARXIV_API = "https://export.arxiv.org/api/query"
ARXIV_RECENT = "https://arxiv.org/list/{category}/recent"
ATOM = "http://www.w3.org/2005/Atom"
ARXIV_NS = "http://arxiv.org/schemas/atom"

RECENT_SHOW_ALL = 2000


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()) if text else ""


def _parse_recent_heading(text: str) -> Optional[datetime]:
    cleaned = _clean(text)
    cleaned = re.sub(r"\s*\(showing.*\)$", "", cleaned)
    try:
        dt = datetime.strptime(cleaned, "%a, %d %b %Y")
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc)


def _parse_atom_datetime(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _calendar_day_range(days_back: int, now: Optional[datetime] = None) -> tuple[date, date]:
    """根据本地日历计算 ``[start_day, end_day]`` 窗口。

    这里故意用本地时间而非 UTC：用户说 "最近 5 天" 是按本地日历理解的，
    而 arXiv recent 页面的 heading 也是不带时区的日期字符串，
    两边保持一致能避免出现 "scraper 抓到了某天但统计表不显示" 的错位。
    """
    if days_back < 1:
        raise ValueError("days_back 必须 >= 1")

    now = now or datetime.now()
    end_day = now.date()
    start_day = end_day - timedelta(days=days_back - 1)
    return start_day, end_day


def calendar_day_range(days_back: int, now: Optional[datetime] = None) -> tuple[date, date]:
    """公开版本的日历窗口计算，供上层打印/展示使用。"""
    return _calendar_day_range(days_back, now)


def _request_text(url: str, params: Optional[Dict[str, object]] = None) -> str:
    try:
        return get_text(url, params=params)
    except RuntimeError as exc:
        raise RuntimeError(f"页面请求失败：{exc}") from exc


def _request_api(params: Dict[str, object]) -> bytes:
    try:
        return get_bytes(ARXIV_API, params=params)
    except RuntimeError as exc:
        raise RuntimeError(f"arXiv API 请求失败：{exc}") from exc


def _extract_recent_entry(
    dt: Tag, dd: Tag, announced_dt: datetime, category: str
) -> Optional[Paper]:
    abs_link = dt.find("a", href=lambda href: href and "/abs/" in href)
    if not abs_link:
        return None

    raw_id = abs_link.get("href", "").split("/abs/")[-1].strip()
    arxiv_id = re.sub(r"v\d+$", "", raw_id)
    if not arxiv_id:
        return None

    title = ""
    authors: List[str] = []
    categories: List[str] = [category]

    title_div = dd.find("div", class_=lambda value: value and "list-title" in value)
    if title_div:
        title = _clean(title_div.get_text(" ", strip=True).replace("Title:", "", 1))

    authors_div = dd.find("div", class_="list-authors")
    if authors_div:
        authors = [_clean(a.get_text(" ", strip=True)) for a in authors_div.find_all("a")]

    subjects_div = dd.find("div", class_="list-subjects")
    if subjects_div:
        text = _clean(subjects_div.get_text(" ", strip=True).replace("Subjects:", "", 1))
        if text:
            categories = [_clean(part) for part in text.split(";") if _clean(part)]

    return Paper.from_recent_entry(
        arxiv_id=arxiv_id,
        title=title,
        authors=authors,
        categories=categories,
        announced_at=announced_dt,
    )


def _scrape_recent_category(category: str, days_back: int) -> List[Paper]:
    url = ARXIV_RECENT.format(category=category)
    html = _request_text(url, params={"show": RECENT_SHOW_ALL})
    soup = BeautifulSoup(html, "html.parser")

    start_day, _ = _calendar_day_range(days_back)
    papers: List[Paper] = []

    for heading in soup.find_all("h3"):
        announced_dt = _parse_recent_heading(heading.get_text(" ", strip=True))
        if not announced_dt:
            continue

        if announced_dt.date() < start_day:
            break

        sibling = heading.next_sibling
        pending_dt: Optional[Tag] = None
        while sibling:
            if isinstance(sibling, Tag):
                if sibling.name == "h3":
                    break
                if sibling.name == "dt":
                    pending_dt = sibling
                elif sibling.name == "dd" and pending_dt is not None:
                    paper = _extract_recent_entry(pending_dt, sibling, announced_dt, category)
                    if paper:
                        papers.append(paper)
                    pending_dt = None
            sibling = sibling.next_sibling

    return papers


def _get_recent_oldest_day(category: str) -> Optional[date]:
    url = ARXIV_RECENT.format(category=category)
    html = _request_text(url, params={"show": RECENT_SHOW_ALL})
    soup = BeautifulSoup(html, "html.parser")

    oldest: Optional[date] = None
    for heading in soup.find_all("h3"):
        announced_dt = _parse_recent_heading(heading.get_text(" ", strip=True))
        if not announced_dt:
            continue
        heading_day = announced_dt.date()
        if oldest is None or heading_day < oldest:
            oldest = heading_day

    return oldest


def _parse_feed(xml_bytes: bytes) -> List[Paper]:
    root = ET.fromstring(xml_bytes)
    papers: List[Paper] = []

    for entry in root.findall(f"{{{ATOM}}}entry"):
        id_url = (entry.findtext(f"{{{ATOM}}}id") or "").strip()
        arxiv_id = re.sub(r"v\d+$", "", id_url.split("/")[-1])
        title = _clean(entry.findtext(f"{{{ATOM}}}title") or "")
        if not arxiv_id or not title:
            continue

        authors: List[str] = []
        affiliations: List[str] = []
        for author in entry.findall(f"{{{ATOM}}}author"):
            name = author.findtext(f"{{{ATOM}}}name")
            if name:
                authors.append(name.strip())
            aff = author.findtext(f"{{{ARXIV_NS}}}affiliation")
            if aff and aff.strip():
                affiliations.append(aff.strip())

        categories = [
            category.get("term", "")
            for category in entry.findall(f"{{{ATOM}}}category")
            if category.get("term")
        ]

        paper = Paper.from_atom_entry(
            {
                "arxiv_id": arxiv_id,
                "title": title,
                "abstract": _clean(entry.findtext(f"{{{ATOM}}}summary") or ""),
                "authors": authors,
                "affiliations": affiliations,
                "categories": categories,
                "comments": _clean(entry.findtext(f"{{{ARXIV_NS}}}comment") or ""),
                "published": (entry.findtext(f"{{{ATOM}}}published") or "").strip(),
                "updated": (entry.findtext(f"{{{ATOM}}}updated") or "").strip(),
            }
        )
        if paper is not None:
            papers.append(paper)

    return papers


def _fetch_metadata_by_ids(ids: List[str], batch_size: int = 50) -> Dict[str, Paper]:
    enriched: Dict[str, Paper] = {}
    total_batches = (len(ids) + batch_size - 1) // batch_size

    for start in range(0, len(ids), batch_size):
        chunk = ids[start : start + batch_size]
        batch_index = start // batch_size + 1
        logger.info(
            "API 元数据补全批次 %d/%d（本批 %d 篇）...",
            batch_index, total_batches, len(chunk),
        )
        params = {"id_list": ",".join(chunk), "max_results": len(chunk)}
        xml_bytes = _request_api(params)
        for paper in _parse_feed(xml_bytes):
            enriched[paper.arxiv_id] = paper

        if start + batch_size < len(ids):
            time.sleep(3)

    return enriched


def fetch_paper_by_id(arxiv_id: str) -> Optional[Paper]:
    """按 arXiv ID 获取单篇论文元信息。"""
    normalized = re.sub(r"v\d+$", "", (arxiv_id or "").strip())
    if not normalized:
        return None

    try:
        enriched_by_id = _fetch_metadata_by_ids([normalized], batch_size=1)
    except Exception as exc:
        raise RuntimeError(f"按 ID 获取论文失败：{exc}") from exc

    return enriched_by_id.get(normalized)


def _dedupe_papers(papers: List[Paper]) -> List[Paper]:
    seen: Dict[str, Paper] = {}
    for paper in papers:
        if not paper.arxiv_id:
            continue
        existing = seen.get(paper.arxiv_id)
        if existing is None:
            seen[paper.arxiv_id] = paper
        else:
            seen[paper.arxiv_id] = existing.merge_non_empty(paper)
    return list(seen.values())


def _sort_papers_by_published_desc(papers: List[Paper]) -> List[Paper]:
    _MIN_DT = datetime.min.replace(tzinfo=timezone.utc)

    def key(paper: Paper) -> datetime:
        return paper.published or _MIN_DT

    return sorted(papers, key=key, reverse=True)


def _enrich_papers_with_api_metadata(papers: List[Paper]) -> List[Paper]:
    ids = [paper.arxiv_id for paper in papers if paper.arxiv_id]
    if not ids:
        return papers

    try:
        logger.info("开始用 arXiv API 补全 %d 篇论文的元数据...", len(ids))
        enriched_by_id = _fetch_metadata_by_ids(ids)
    except Exception as exc:
        logger.warning("元数据补全失败，继续使用页面抓取结果：%s", exc)
        return papers

    merged: List[Paper] = []
    for paper in papers:
        from_api = enriched_by_id.get(paper.arxiv_id)
        if from_api is None:
            merged.append(paper)
            continue
        # API 补全提供 abstract / 真实 published / 详细 authors 等，
        # 用 non-empty 合并策略：不会覆盖 recent 页面已有的 announced_date 等。
        merged.append(paper.merge_non_empty(from_api))

    return merged


def fetch_recent_papers(
    days_back: int = DAYS_BACK,
    categories: Optional[List[str]] = None,
    max_results: Optional[int] = ARXIV_MAX_RESULTS,
    enrich_metadata: bool = False,
) -> List[Paper]:
    """抓取最近 N 天的论文。"""
    if days_back < 1:
        raise ValueError("days_back 必须 >= 1")

    categories = categories or FETCH_CATEGORIES
    all_papers: List[Paper] = []

    logger.info("查询分区：%s", ", ".join(categories))
    logger.info("时间范围：最近 %d 天", days_back)

    for category in categories:
        logger.info("抓取 %s recent 页面...", category)
        papers = _scrape_recent_category(category, days_back=days_back)
        logger.info("%s 获取 %d 篇", category, len(papers))
        all_papers.extend(papers)
        time.sleep(1)

    deduped = _dedupe_papers(all_papers)
    sorted_papers = _sort_papers_by_published_desc(deduped)
    limited = sorted_papers[:max_results] if max_results is not None else sorted_papers

    if enrich_metadata:
        limited = _enrich_papers_with_api_metadata(limited)

    logger.info("共获取 %d 篇论文", len(limited))
    return limited


def fetch_papers(
    days_back: int = DAYS_BACK,
    categories: Optional[List[str]] = None,
) -> List[Paper]:
    """主流程入口：先抓 recent 页面，再尽量补全元数据。"""
    return fetch_recent_papers(
        days_back=days_back,
        categories=categories,
        enrich_metadata=True,
    )


def get_recent_coverage(
    categories: Optional[List[str]] = None,
) -> Tuple[Optional[date], Dict[str, Optional[date]]]:
    """返回 recent 页面能覆盖到的最早日期。"""
    categories = categories or FETCH_CATEGORIES
    per_category: Dict[str, Optional[date]] = {}
    oldest_overall: Optional[date] = None

    for category in categories:
        oldest = _get_recent_oldest_day(category)
        per_category[category] = oldest
        if oldest and (oldest_overall is None or oldest < oldest_overall):
            oldest_overall = oldest

    return oldest_overall, per_category
