#!/usr/bin/env python3
"""
paper_radio — 每日 arXiv 论文摘要工具
用法：python main.py [--days N] [--output FILE]
"""
import argparse
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()  # 读取 .env 文件，必须在 import config 之前

import config
from logging_config import setup_logging
from recent_report import parse_categories_arg, weekday_cn
from pipeline.run import run_mining_pipeline


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
    parser.add_argument(
        "--auto-deep-analysis",
        action="store_true",
        help="兼容旧行为：主流程中自动对高分论文生成深度分析",
    )
    args = parser.parse_args()
    categories = parse_categories_arg(args.categories, config.FETCH_CATEGORIES)

    now = datetime.now()

    print("=" * 60)
    print(f"📡 Paper Radio | {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   追溯 {args.days} 天内的 arXiv 新论文")
    print(f"   分区: {', '.join(categories)}")
    print(f"   自动精读: {'开启' if args.auto_deep_analysis else '关闭（Dashboard 按需触发）'}")
    print("=" * 60)

    def on_progress(message: str, progress: int) -> None:
        print(f"[{progress:3d}%] {message}")

    result = run_mining_pipeline(
        days=args.days,
        categories=categories,
        output=args.output,
        auto_deep_analysis=args.auto_deep_analysis,
        progress_callback=on_progress,
    )

    if not result.fetched_count:
        print("\n⚠️  未找到最近的相关论文，可能是周末或网络问题。")
        return

    print(f"\n     共获取 {result.fetched_count} 篇候选论文")
    if result.daily_counts:
        print("     每日 announce 数量：")
        total = sum(count for _, count in result.daily_counts)
        for day, count in result.daily_counts:
            try:
                dt = datetime.strptime(day, "%Y-%m-%d")
                label = f"{day} ({weekday_cn(dt)})"
            except ValueError:
                label = day
            print(f"       - {label}: {count} 篇")
        if total != result.fetched_count:
            print(f"       (注：有 {result.fetched_count - total} 篇缺少 announce 日期)")

    print("\n" + "=" * 60)
    print("✅ 已按 announced_date 生成以下日报：")
    for item in result.day_results:
        print(f"   - {item.date}: {item.daily_report_path}")
    if result.errors:
        print("⚠️  部分步骤有错误：")
        for error in result.errors:
            print(f"   - {error}")
    print("=" * 60)


if __name__ == "__main__":
    main()
