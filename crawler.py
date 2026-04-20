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


def _extract_recent_entry(dt: Tag, dd: Tag, announced_dt: datetime, category: str) -> Optional[Dict]:
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

    announced_str = announced_dt.strftime("%Y-%m-%dT00:00:00Z")
    announced_day = announced_dt.strftime("%Y-%m-%d")
    return {
        "arxiv_id": arxiv_id,
        "abs_url": f"https://arxiv.org/abs/{arxiv_id}",
        "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
        "title": title,
        "abstract": "",
        "authors": authors,
        "affiliations": [],
        "published": announced_str,
        "updated": announced_str,
        # arXiv recent 页面的 announce 日期（不会被 API 补全覆盖，供每日统计使用）
        "announced_date": announced_day,
        "categories": categories,
    }


def _scrape_recent_category(category: str, days_back: int) -> List[Dict]:
    url = ARXIV_RECENT.format(category=category)
    html = _request_text(url, params={"show": RECENT_SHOW_ALL})
    soup = BeautifulSoup(html, "html.parser")

    start_day, _ = _calendar_day_range(days_back)
    papers: List[Dict] = []

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


def _parse_feed(xml_bytes: bytes) -> List[Dict]:
    root = ET.fromstring(xml_bytes)
    papers: List[Dict] = []

    for entry in root.findall(f"{{{ATOM}}}entry"):
        id_url = (entry.findtext(f"{{{ATOM}}}id") or "").strip()
        arxiv_id = re.sub(r"v\d+$", "", id_url.split("/")[-1])
        title = _clean(entry.findtext(f"{{{ATOM}}}title") or "")
        abstract = _clean(entry.findtext(f"{{{ATOM}}}summary") or "")
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

        papers.append(
            {
                "arxiv_id": arxiv_id,
                "abs_url": f"https://arxiv.org/abs/{arxiv_id}",
                "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
                "title": title,
                "abstract": abstract,
                "authors": authors,
                "affiliations": affiliations,
                "published": (entry.findtext(f"{{{ATOM}}}published") or "").strip(),
                "updated": (entry.findtext(f"{{{ATOM}}}updated") or "").strip(),
                "categories": categories,
            }
        )

    return papers


def _fetch_metadata_by_ids(ids: List[str], batch_size: int = 50) -> Dict[str, Dict]:
    enriched: Dict[str, Dict] = {}
    total_batches = (len(ids) + batch_size - 1) // batch_size

    for start in range(0, len(ids), batch_size):
        chunk = ids[start : start + batch_size]
        batch_index = start // batch_size + 1
        print(
            f"  → API 元数据补全批次 {batch_index}/{total_batches}"
            f"（本批 {len(chunk)} 篇）..."
        )
        params = {"id_list": ",".join(chunk), "max_results": len(chunk)}
        xml_bytes = _request_api(params)
        for paper in _parse_feed(xml_bytes):
            enriched[paper["arxiv_id"]] = paper

        if start + batch_size < len(ids):
            time.sleep(3)

    return enriched


def fetch_paper_by_id(arxiv_id: str) -> Optional[Dict]:
    """按 arXiv ID 获取单篇论文元信息。"""
    arxiv_id = re.sub(r"v\d+$", "", (arxiv_id or "").strip())
    if not arxiv_id:
        return None

    try:
        enriched_by_id = _fetch_metadata_by_ids([arxiv_id], batch_size=1)
    except Exception as exc:
        raise RuntimeError(f"按 ID 获取论文失败：{exc}") from exc

    return enriched_by_id.get(arxiv_id)


def _merge_paper_non_empty(existing: Dict, incoming: Dict) -> Dict:
    """将 ``incoming`` 合并进 ``existing``，但仅当 incoming 字段非空时才覆盖。

    解决问题：同一篇论文从两个分区被抓到时，第二次的空 abstract / authors
    不应该覆盖第一次已经拿到的值。
    """
    merged = dict(existing)
    for key, value in incoming.items():
        # None / 空串 / 空列表 一律视作“没有新值”
        if value in (None, "", [], {}):
            continue
        merged[key] = value
    return merged


def _dedupe_papers(papers: List[Dict]) -> List[Dict]:
    seen: Dict[str, Dict] = {}
    for paper in papers:
        arxiv_id = paper.get("arxiv_id")
        if not arxiv_id:
            continue
        existing = seen.get(arxiv_id)
        if existing is None:
            seen[arxiv_id] = paper
        else:
            seen[arxiv_id] = _merge_paper_non_empty(existing, paper)

    return list(seen.values())


def _sort_papers_by_published_desc(papers: List[Dict]) -> List[Dict]:
    def key(paper: Dict) -> datetime:
        dt = _parse_atom_datetime(paper.get("published", ""))
        return dt or datetime.min.replace(tzinfo=timezone.utc)

    return sorted(papers, key=key, reverse=True)


def _enrich_papers_with_api_metadata(papers: List[Dict]) -> List[Dict]:
    ids = [paper["arxiv_id"] for paper in papers if paper.get("arxiv_id")]
    if not ids:
        return papers

    try:
        print(f"  → 开始用 arXiv API 补全 {len(ids)} 篇论文的元数据...")
        enriched_by_id = _fetch_metadata_by_ids(ids)
    except Exception as exc:
        print(f"  ⚠️  元数据补全失败，继续使用页面抓取结果：{exc}")
        return papers

    merged: List[Dict] = []
    for paper in papers:
        aid = paper["arxiv_id"]
        merged.append({**paper, **enriched_by_id.get(aid, {})})

    return merged


def fetch_recent_papers(
    days_back: int = DAYS_BACK,
    categories: Optional[List[str]] = None,
    max_results: Optional[int] = ARXIV_MAX_RESULTS,
    enrich_metadata: bool = False,
) -> List[Dict]:
    """抓取最近 N 天的论文。"""
    if days_back < 1:
        raise ValueError("days_back 必须 >= 1")

    categories = categories or FETCH_CATEGORIES
    all_papers: List[Dict] = []

    print(f"  → 查询分区：{', '.join(categories)}")
    print(f"  → 时间范围：最近 {days_back} 天")

    for category in categories:
        print(f"  → 抓取 {category} recent 页面...")
        papers = _scrape_recent_category(category, days_back=days_back)
        print(f"     获取 {len(papers)} 篇")
        all_papers.extend(papers)
        time.sleep(1)

    deduped = _dedupe_papers(all_papers)
    sorted_papers = _sort_papers_by_published_desc(deduped)
    limited = sorted_papers[:max_results] if max_results is not None else sorted_papers

    if enrich_metadata:
        limited = _enrich_papers_with_api_metadata(limited)

    print(f"  ✅ 共获取 {len(limited)} 篇论文")
    return limited


def fetch_papers(
    days_back: int = DAYS_BACK,
    categories: Optional[List[str]] = None,
) -> List[Dict]:
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
