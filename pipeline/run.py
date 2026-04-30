"""Reusable mining pipeline shared by CLI and dashboard jobs."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Sequence

import config
from crawler import calendar_day_range, fetch_papers
from recent_report import save_recent_crawl_report, summarize_daily_counts
from ranker import enrich_papers_with_institutions, run_stage1_filter, run_stage2_rank
from reporter import generate_report_bundle
from score_adjust import apply_score_adjustments
from selected_report import save_selected_report
from serializers import build_selected_json_payload, refresh_reports_index, write_json

ProgressCallback = Callable[[str, int], None]
CancelCheck = Callable[[], bool]


class PipelineCanceled(RuntimeError):
    """Raised when the caller requests a cooperative pipeline cancel."""


@dataclass
class DayPipelineResult:
    date: str
    fetched_count: int = 0
    selected_count: int = 0
    ranked_count: int = 0
    selected_report_path: str = ""
    daily_report_path: str = ""
    selected_json_path: str = ""
    daily_json_path: str = ""
    errors: List[str] = field(default_factory=list)


@dataclass
class PipelineResult:
    days: int
    categories: List[str]
    date_range: str
    fetched_count: int
    crawl_report_path: str = ""
    index_json_path: str = ""
    daily_counts: List[tuple[str, int]] = field(default_factory=list)
    day_results: List[DayPipelineResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "days": self.days,
            "categories": self.categories,
            "date_range": self.date_range,
            "fetched_count": self.fetched_count,
            "crawl_report_path": self.crawl_report_path,
            "index_json_path": self.index_json_path,
            "daily_counts": self.daily_counts,
            "day_results": [item.__dict__ for item in self.day_results],
            "errors": self.errors,
        }


def _emit(callback: ProgressCallback | None, message: str, progress: int) -> None:
    if callback:
        callback(message, progress)


def _check_cancel(cancel_check: CancelCheck | None) -> None:
    if cancel_check and cancel_check():
        raise PipelineCanceled("任务已取消")


def group_papers_by_announced_day(papers):
    grouped = defaultdict(list)
    for paper in papers:
        grouped[paper.announced_day or "unknown"].append(paper)
    return sorted(grouped.items(), key=lambda item: item[0], reverse=True)


def run_mining_pipeline(
    *,
    days: int,
    categories: Sequence[str],
    output: str | None = None,
    auto_deep_analysis: bool = False,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> PipelineResult:
    now = datetime.now()
    start_day, end_day = calendar_day_range(days, now=now)
    date_range_str = f"{start_day.strftime('%Y-%m-%d')} ~ {end_day.strftime('%Y-%m-%d')}"
    categories = list(categories)

    _emit(progress_callback, f"开始抓取 arXiv：{date_range_str}，分区 {', '.join(categories)}", 5)
    _check_cancel(cancel_check)
    papers = fetch_papers(days_back=days, categories=categories)
    _check_cancel(cancel_check)
    result = PipelineResult(
        days=days,
        categories=categories,
        date_range=date_range_str,
        fetched_count=len(papers),
        daily_counts=summarize_daily_counts(papers),
    )

    if not papers:
        _emit(progress_callback, "未获取到论文，结束任务", 100)
        return result

    crawl_snapshot_path = save_recent_crawl_report(
        output_dir=config.CRAWL_OUTPUT_DIR,
        now=now,
        days_back=days,
        categories=categories,
        papers=papers,
        date_range=date_range_str,
    )
    result.crawl_report_path = str(crawl_snapshot_path)
    _emit(progress_callback, f"抓取快照已保存：{crawl_snapshot_path}", 18)
    _check_cancel(cancel_check)

    grouped_days = group_papers_by_announced_day(papers)
    total_groups = max(1, len(grouped_days))

    for index, (day, day_papers) in enumerate(grouped_days, 1):
        base_progress = 18 + int((index - 1) / total_groups * 68)
        day_result = DayPipelineResult(date=day, fetched_count=len(day_papers))
        _emit(progress_callback, f"处理 {day}：{len(day_papers)} 篇论文", base_progress)

        try:
            _check_cancel(cancel_check)
            candidates = run_stage1_filter(day_papers)
            day_result.selected_count = len(candidates)
            _emit(progress_callback, f"{day} 标题粗筛后进入 Longlist：{len(candidates)} 篇", base_progress + 10)
            _check_cancel(cancel_check)

            if candidates:
                enriched = enrich_papers_with_institutions(candidates)
                _emit(progress_callback, f"{day} 机构推断完成，开始摘要精排", base_progress + 24)
                _check_cancel(cancel_check)
                ranked = run_stage2_rank(enriched)
                _check_cancel(cancel_check)
                ranked = apply_score_adjustments(ranked)
            else:
                ranked = []
            day_result.ranked_count = len(ranked)
            _check_cancel(cancel_check)

            export_now = datetime.now()
            selected_snapshot_path = save_selected_report(
                output_dir=config.SELECTED_OUTPUT_DIR,
                now=export_now,
                ranked_papers=ranked,
                report_date=day,
            )
            day_result.selected_report_path = str(selected_snapshot_path)
            _check_cancel(cancel_check)

            report, daily_payload = generate_report_bundle(
                ranked,
                categories=categories,
                report_date=day,
                auto_deep_analysis=auto_deep_analysis,
            )
            _check_cancel(cancel_check)

            if output and len(grouped_days) == 1:
                output_path = Path(output)
            else:
                config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                output_path = config.OUTPUT_DIR / f"daily_report_{day}.md"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(report, encoding="utf-8")
            day_result.daily_report_path = str(output_path)

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
            daily_json_path = write_json(
                config.DAILY_JSON_OUTPUT_DIR / f"daily_report_{day}.json",
                daily_payload,
            )
            day_result.selected_json_path = str(selected_json_path)
            day_result.daily_json_path = str(daily_json_path)
            _emit(progress_callback, f"{day} 报告与前端 JSON 已生成", base_progress + 58)
        except PipelineCanceled:
            raise
        except Exception as exc:
            message = f"{day} 处理失败：{exc}"
            day_result.errors.append(message)
            result.errors.append(message)
            _emit(progress_callback, message, base_progress + 58)

        result.day_results.append(day_result)

    try:
        _check_cancel(cancel_check)
        index_json_path = refresh_reports_index(
            index_path=config.REPORTS_JSON_DIR / "index.json",
            daily_dir=config.DAILY_JSON_OUTPUT_DIR,
            selected_dir=config.SELECTED_JSON_OUTPUT_DIR,
            categories=categories,
        )
        result.index_json_path = str(index_json_path)
        _emit(progress_callback, f"前端索引已刷新：{index_json_path}", 95)
    except Exception as exc:
        message = f"前端索引刷新失败：{exc}"
        result.errors.append(message)
        _emit(progress_callback, message, 95)

    _emit(progress_callback, "任务完成", 100)
    return result
