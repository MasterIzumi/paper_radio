#!/usr/bin/env python3
"""
paper_radio — 每日 arXiv 论文摘要工具
用法：python main.py [--days N] [--output FILE]
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()  # 读取 .env 文件，必须在 import config 之前

import config
from logging_config import setup_logging
from crawler import calendar_day_range, fetch_papers
from recent_report import (
    parse_categories_arg,
    save_recent_crawl_report,
    summarize_daily_counts,
    weekday_cn,
)
from ranker import enrich_top_papers_with_institutions, rank_papers
from reporter import generate_report
from selected_report import save_selected_report


def main():
    setup_logging()

    parser = argparse.ArgumentParser(description="每日 arXiv 论文摘要生成器")
    parser.add_argument(
        "--days", type=int, default=config.DAYS_BACK,
        help=f"向前追溯天数（默认 {config.DAYS_BACK}）",
    )
    parser.add_argument(
        "--categories",
        type=str,
        default=",".join(config.FETCH_CATEGORIES),
        help=f"分区列表，逗号分隔（默认 {','.join(config.FETCH_CATEGORIES)}）",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="输出文件路径（默认 reports/daily_report_YYYY-MM-DD.md）",
    )
    args = parser.parse_args()
    categories = parse_categories_arg(args.categories, config.FETCH_CATEGORIES)

    now = datetime.now()
    start_day, end_day = calendar_day_range(args.days, now=now)
    date_range_str = f"{start_day.strftime('%Y-%m-%d')} ~ {end_day.strftime('%Y-%m-%d')}"

    print("=" * 60)
    print(f"📡 Paper Radio | {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   追溯 {args.days} 天内的 arXiv 新论文")
    print(f"   查询日期范围：{date_range_str}")
    print(f"   分区: {', '.join(categories)}")
    print("=" * 60)

    # Step 1: 爬取
    print("\n[1/3] 正在从 arXiv 获取论文...")
    papers = fetch_papers(days_back=args.days, categories=categories)

    if not papers:
        print("\n⚠️  未找到最近的相关论文，可能是周末或网络问题。")
        sys.exit(0)

    print(f"     共获取 {len(papers)} 篇候选论文")

    daily_counts = summarize_daily_counts(papers)
    if daily_counts:
        print("     每日 announce 数量：")
        total = sum(count for _, count in daily_counts)
        for day, count in daily_counts:
            try:
                dt = datetime.strptime(day, "%Y-%m-%d")
                label = f"{day} ({weekday_cn(dt)})"
            except ValueError:
                label = day
            print(f"       - {label}: {count} 篇")
        if total != len(papers):
            print(f"       (注：有 {len(papers) - total} 篇缺少 announce 日期)")

    crawl_snapshot_path = save_recent_crawl_report(
        output_dir=config.CRAWL_OUTPUT_DIR,
        now=now,
        days_back=args.days,
        categories=categories,
        papers=papers,
        date_range=date_range_str,
    )
    print(f"     抓取快照已保存：{crawl_snapshot_path}")

    # Step 2: 筛选与排序
    print("\n[2/3] 正在筛选并排序候选论文...")
    ranked = rank_papers(papers)
    print(f"     筛选出 TOP {len(ranked)} 篇论文")

    selected_snapshot_path = save_selected_report(
        output_dir=config.SELECTED_OUTPUT_DIR,
        now=datetime.now(),
        ranked_papers=ranked,
    )
    print(f"     入选快照已保存：{selected_snapshot_path}")

    # Step 3: 生成报告
    print("\n[3/3] 正在补充 TOP 10 机构信息并生成日报...")
    ranked_for_report = enrich_top_papers_with_institutions(ranked, top_k=10)
    report = generate_report(ranked_for_report)

    # 保存
    date_str = datetime.now().strftime("%Y-%m-%d")
    if args.output:
        output_path = Path(args.output)
    else:
        config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = config.OUTPUT_DIR / f"daily_report_{date_str}.md"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")

    print("\n" + "=" * 60)
    print(f"✅ 报告已保存至：{output_path}")
    print("=" * 60)

    # 打印报告前几行预览
    preview = "\n".join(report.splitlines()[:20])
    print(f"\n{'─'*60}\n{preview}\n{'─'*60}")


if __name__ == "__main__":
    main()
