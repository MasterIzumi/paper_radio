#!/usr/bin/env python3
"""测试最近 N 天 arXiv 论文抓取，并以表格输出结果。"""
from __future__ import annotations

import argparse
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

import config
from crawler import calendar_day_range, fetch_recent_papers, get_recent_coverage
from recent_report import (
    build_daily_counts_by_category,
    build_paper_table_rows,
    parse_categories_arg,
    render_table,
    save_recent_crawl_report,
    summarize_daily_counts,
    weekday_cn,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="测试 arXiv 最近 N 天论文抓取")
    parser.add_argument(
        "--days",
        type=int,
        default=config.DAYS_BACK,
        help=f"向前追溯天数（默认 {config.DAYS_BACK}）",
    )
    parser.add_argument(
        "--categories",
        type=str,
        default=",".join(config.FETCH_CATEGORIES),
        help=f"分区列表，逗号分隔（默认 {','.join(config.FETCH_CATEGORIES)}）",
    )
    args = parser.parse_args()
    categories = parse_categories_arg(args.categories, config.FETCH_CATEGORIES)
    now = datetime.now()
    coverage_note = ""

    start_day, end_day = calendar_day_range(args.days, now=now)
    date_range_str = f"{start_day.strftime('%Y-%m-%d')} ~ {end_day.strftime('%Y-%m-%d')}"

    print("=" * 80)
    print(f"arXiv 最近 {args.days} 天论文抓取测试 | {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"分区: {', '.join(categories)}")
    print(f"参数: days={args.days}, categories={','.join(categories)}")
    print(f"查询日期范围：{date_range_str}（本地时间）")
    print("说明: 每日统计展示全量抓取结果；论文列表也展示本次抓取到的全量论文。")
    print("=" * 80)

    try:
        oldest_overall, oldest_by_category = get_recent_coverage(categories=categories)
    except Exception as exc:
        oldest_overall, oldest_by_category = None, {}
        print(f"recent 覆盖范围探测失败：{exc}")

    if oldest_overall is not None:
        covered_days = (datetime.now().date() - oldest_overall).days + 1
        if args.days > covered_days:
            coverage_note = (
                f"提示：当前 recent 页面最早只覆盖到 {oldest_overall.strftime('%Y-%m-%d')}，"
                f"约最近 {covered_days} 个自然日。你请求了 {args.days} 天，超出部分无法从 recent 页面获取。"
            )
            print(coverage_note)
            details = ", ".join(
                f"{category}={day.strftime('%Y-%m-%d') if day else '未知'}"
                for category, day in oldest_by_category.items()
            )
            print(f"各分区最早日期：{details}")
            coverage_note = f"{coverage_note} 各分区最早日期：{details}"

    try:
        papers = fetch_recent_papers(
            days_back=args.days,
            categories=categories,
            max_results=None,
        )
    except Exception as exc:
        print(f"\n抓取失败：{exc}")
        return

    print(f"\n共抓取到 {len(papers)} 篇论文。")

    if not papers:
        print("未抓到论文，请检查网络、分区配置或时间范围。")
        return

    daily_counts = summarize_daily_counts(papers)
    if daily_counts:
        print("每日 announce 数量：")
        total = sum(count for _, count in daily_counts)
        for day, count in daily_counts:
            try:
                dt = datetime.strptime(day, "%Y-%m-%d")
                label = f"{day} ({weekday_cn(dt)})"
            except ValueError:
                label = day
            print(f"  - {label}: {count} 篇")
        if total != len(papers):
            print(f"  (注：有 {len(papers) - total} 篇缺少 announce 日期)")

    daily_headers, daily_rows = build_daily_counts_by_category(papers, args.days, categories, now=now)
    daily_table = render_table(daily_rows, headers=daily_headers)
    print("\n每日统计：")
    print(daily_table)

    table = render_table(
        build_paper_table_rows(papers),
        headers=["#", "arXiv ID", "Title", "Authors", "Subjects", "URL", "Published"],
    )
    print("\n论文列表：")
    print(table)

    output_path = save_recent_crawl_report(
        output_dir=config.CRAWL_OUTPUT_DIR,
        now=now,
        days_back=args.days,
        categories=categories,
        papers=papers,
        coverage_note=coverage_note,
        date_range=date_range_str,
    )
    print(f"\nMarkdown 已保存至：{output_path}")


if __name__ == "__main__":
    main()
