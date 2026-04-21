#!/usr/bin/env python3
"""测试单篇 arXiv 论文的作者机构推断。"""
from __future__ import annotations

import argparse

from dotenv import load_dotenv

load_dotenv()

from crawler import fetch_paper_by_id
from logging_config import setup_logging
from models import RankedPaper
from pdf_context import fetch_pdf_first_page_context
from ranker import infer_paper_institutions


def _fmt_list(values: list[str], fallback: str = "N/A") -> str:
    cleaned = [str(value).strip() for value in values if str(value).strip()]
    return "; ".join(cleaned) if cleaned else fallback


def main() -> None:
    setup_logging()

    parser = argparse.ArgumentParser(description="测试 arXiv 论文机构推断")
    parser.add_argument(
        "--paper-id",
        required=True,
        help="arXiv 论文 ID，例如 2504.12345",
    )
    args = parser.parse_args()

    print("=" * 80)
    print(f"单篇论文机构推断测试 | paper_id={args.paper_id}")
    print("=" * 80)

    try:
        paper = fetch_paper_by_id(args.paper_id)
    except Exception as exc:
        print(f"\n获取论文失败：{exc}")
        return

    if paper is None:
        print("\n未找到对应论文，请检查 arXiv paper id 是否正确。")
        return

    print("\n[1/2] 已获取论文元信息")
    print(f"Title: {paper.title or 'N/A'}")
    print(f"Authors: {_fmt_list(paper.authors, fallback='Unknown')}")
    print(f"Raw Affiliations: {_fmt_list(paper.affiliations)}")
    print(f"URL: {paper.abs_url}")

    pdf_context = fetch_pdf_first_page_context(paper.arxiv_id, pdf_url=paper.pdf_url)
    ranked = RankedPaper.from_paper(paper)
    if pdf_context:
        print(f"PDF First Page Context: {pdf_context}")
        ranked = ranked.with_institutions(
            raw_affiliations=paper.affiliations,
            merged_affiliations=paper.affiliations,
            pdf_first_page_context=pdf_context,
        )
    else:
        print("PDF First Page Context: N/A")

    print("\n[2/2] 正在进行机构归一与推断...")
    try:
        enriched = infer_paper_institutions(ranked)
    except Exception as exc:
        print(f"\n机构推断失败：{exc}")
        return

    if enriched is None:
        print("\n推断未返回结果。")
        return

    print("\n推断结果：")
    print(f"- paper_id: {enriched.arxiv_id}")
    print(f"- institution_types: {enriched.institution_types}")
    print(f"- evidence_source: {enriched.institution_evidence_source}")
    print(f"- normalized_institutions: {_fmt_list(enriched.normalized_institutions)}")
    print(f"- institution_summary: {enriched.institution_summary or 'N/A'}")
    print(f"- merged_affiliations: {_fmt_list(enriched.affiliations)}")


if __name__ == "__main__":
    main()
