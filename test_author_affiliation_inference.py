#!/usr/bin/env python3
"""测试单篇 arXiv 论文的作者机构推断。"""
from __future__ import annotations

import argparse

from dotenv import load_dotenv

load_dotenv()

from crawler import fetch_paper_by_id
from pdf_context import fetch_pdf_first_page_context
from ranker import infer_paper_institutions


def _fmt_list(values: list[str], fallback: str = "N/A") -> str:
    cleaned = [str(value).strip() for value in values if str(value).strip()]
    return "; ".join(cleaned) if cleaned else fallback


def main() -> None:
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

    if not paper:
        print("\n未找到对应论文，请检查 arXiv paper id 是否正确。")
        return

    print("\n[1/2] 已获取论文元信息")
    print(f"Title: {paper.get('title', 'N/A')}")
    print(f"Authors: {_fmt_list(paper.get('authors', []), fallback='Unknown')}")
    print(f"Raw Affiliations: {_fmt_list(paper.get('affiliations', []))}")
    print(f"URL: {paper.get('abs_url', '')}")

    pdf_context = fetch_pdf_first_page_context(
        args.paper_id,
        pdf_url=paper.get("pdf_url", ""),
    )
    if pdf_context:
        print(f"PDF First Page Context: {pdf_context}")
        paper = {**paper, "pdf_first_page_context": pdf_context}
    else:
        print("PDF First Page Context: N/A")

    print("\n[2/2] 正在进行机构归一与推断...")
    try:
        enriched = infer_paper_institutions(paper)
    except Exception as exc:
        print(f"\n机构推断失败：{exc}")
        return

    print("\n推断结果：")
    print(f"- paper_id: {enriched.get('arxiv_id', '')}")
    print(f"- institution_types: {enriched.get('institution_types', 'unknown')}")
    print(f"- evidence_source: {enriched.get('institution_evidence_source', 'unknown')}")
    print(f"- normalized_institutions: {_fmt_list(enriched.get('normalized_institutions', []))}")
    print(f"- institution_summary: {enriched.get('institution_summary', 'N/A') or 'N/A'}")
    print(f"- merged_affiliations: {_fmt_list(enriched.get('affiliations', []))}")


if __name__ == "__main__":
    main()
