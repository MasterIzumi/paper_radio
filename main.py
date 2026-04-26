#!/usr/bin/env python3
"""
paper_radio — 每日 arXiv 论文摘要工具
用法：python main.py [--days N] [--output FILE]
"""
import argparse
import sys
from collections import defaultdict
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
from ranker import (
    enrich_papers_with_institutions,
    run_stage1_filter,
    run_stage2_rank,
)
from reporter import generate_report_bundle
from score_adjust import apply_score_adjustments
from serializers import (
    build_selected_json_payload,
    refresh_reports_index,
    write_json,
)
from selected_report import save_selected_report


def _group_papers_by_announced_day(papers):
    grouped = defaultdict(list)
    for paper in papers:
        grouped[paper.announced_day or "unknown"].append(paper)
    return sorted(grouped.items(), key=lambda item: item[0], reverse=True)


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

    grouped_days = _group_papers_by_announced_day(papers)

    if args.output and len(grouped_days) != 1:
        print("⚠️  检测到多天 announced 结果，忽略自定义 --output，改为按日期分别落盘。")

    print(f"\n[2/3] 正在按 announced_date 分天筛选、评分与补充机构信息...")
    generated_reports = []
    generated_selected = []

    for day, day_papers in grouped_days:
        print(f"\n  - 处理 {day}：{len(day_papers)} 篇论文")
        candidates = run_stage1_filter(day_papers)
        print(f"    标题粗筛后进入 selected 集：{len(candidates)} 篇")

        if candidates:
            print(f"    为 {len(candidates)} 篇 selected 论文并行补充机构信息...")
            enriched = enrich_papers_with_institutions(candidates)

            print("    对 selected 论文进行摘要精排...")
            ranked = run_stage2_rank(enriched)
            print(f"    精排完成，共 {len(ranked)} 篇论文拿到分数")

            print("    叠加 featured author / 顶会录用加分...")
            ranked = apply_score_adjustments(ranked)
        else:
            ranked = []

        export_now = datetime.now()
        selected_snapshot_path = save_selected_report(
            output_dir=config.SELECTED_OUTPUT_DIR,
            now=export_now,
            ranked_papers=ranked,
            report_date=day,
        )
        generated_selected.append(selected_snapshot_path)
        print(f"    入选快照已保存：{selected_snapshot_path}")

        report, daily_payload = generate_report_bundle(
            ranked,
            categories=categories,
            report_date=day,
        )

        if args.output and len(grouped_days) == 1:
            output_path = Path(args.output)
        else:
            config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            output_path = config.OUTPUT_DIR / f"daily_report_{day}.md"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        generated_reports.append((day, output_path, report))

        try:
            selected_payload = build_selected_json_payload(
                now=export_now,
                ranked_papers=ranked,
                categories=categories,
                report_date=day,
            )
            selected_json_path = write_json(
                config.SELECTED_JSON_OUTPUT_DIR / f"selected_papers_{day}.json",
                selected_payload,
            )
            write_json(
                config.WEBAPP_SELECTED_JSON_OUTPUT_DIR / f"selected_papers_{day}.json",
                selected_payload,
            )
            daily_json_path = write_json(
                config.DAILY_JSON_OUTPUT_DIR / f"daily_report_{day}.json",
                daily_payload,
            )
            write_json(
                config.WEBAPP_DAILY_JSON_OUTPUT_DIR / f"daily_report_{day}.json",
                daily_payload,
            )
            print(f"    前端数据已更新：{selected_json_path}")
            print(f"    前端数据已更新：{daily_json_path}")
        except Exception as exc:
            print(f"⚠️  {day} 的前端 JSON 导出失败，Markdown 已保留：{exc}")

    print("\n[3/3] 正在刷新前端索引...")
    try:
        index_json_path = refresh_reports_index(
            index_path=config.REPORTS_JSON_DIR / "index.json",
            daily_dir=config.DAILY_JSON_OUTPUT_DIR,
            selected_dir=config.SELECTED_JSON_OUTPUT_DIR,
            categories=categories,
        )
        refresh_reports_index(
            index_path=config.WEBAPP_REPORTS_JSON_DIR / "index.json",
            daily_dir=config.WEBAPP_DAILY_JSON_OUTPUT_DIR,
            selected_dir=config.WEBAPP_SELECTED_JSON_OUTPUT_DIR,
            categories=categories,
        )
        print(f"     前端索引已更新：{index_json_path}")
    except Exception as exc:
        print(f"⚠️  前端索引刷新失败：{exc}")

    print("\n" + "=" * 60)
    print("✅ 已按 announced_date 生成以下日报：")
    for day, output_path, _ in generated_reports:
        print(f"   - {day}: {output_path}")
    print("=" * 60)

    if generated_reports:
        preview = "\n".join(generated_reports[0][2].splitlines()[:20])
        print(f"\n{'─'*60}\n{preview}\n{'─'*60}")


if __name__ == "__main__":
    main()
