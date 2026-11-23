"""任务监控与数据质量服务（阶段四 · 步骤 1-4）。

    read_task_log()            解析 ETL 任务日志（backend/etl/logs/task_run.log）
    get_task_status()          汇总各任务最近一次运行状态
    trigger_task(...)          手动触发指定任务（白名单 + 懒加载 ETL 模块）
    load_quality_report(...)   读取指定批次的数据质量报告 JSON
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from app.core.response import BusinessError

# ETL 日志与报告目录（可用 Settings.etl_log_dir 覆盖）
_LOG_DIR = Path(__file__).resolve().parents[2] / "etl" / "logs"

TASK_NAMES: list[str] = [
    "init_dim",
    "extract_ods",
    "clean_dwd",
    "quality_check",
    "dwd_wide",
    "aggregate_dws",
    "ads_indicators",
    "indicator_reconcile",
]

# 允许通过接口手动触发的任务（质量与对账为只读校验，不提供触发）
TRIGGERABLE_TASKS: set[str] = {"extract_ods", "clean_dwd", "dwd_wide", "aggregate_dws", "ads_indicators"}

# 任务名 -> 执行函数（测试可替换），签名 (start_date, end_date) -> dict | int
TASK_RUNNERS: dict[str, Callable[[str, str], Any]] = {}


def _log_dir() -> Path:
    try:
        from app.core.config import get_settings

        configured = get_settings().etl_log_dir
    except Exception:  # noqa: BLE001
        configured = ""
    return Path(configured) if configured else _LOG_DIR


def task_log_path() -> Path:
    """任务日志文件路径。"""
    return _log_dir() / "task_run.log"


def read_task_log(log_file: Path | str | None = None) -> list[dict[str, Any]]:
    """解析任务日志（JSON Lines），返回按时间正序的记录列表。"""
    path = Path(log_file) if log_file else task_log_path()
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def get_task_status(log_file: Path | str | None = None) -> dict[str, Any]:
    """汇总每个任务最近一次运行状态。"""
    records = read_task_log(log_file)
    latest: dict[str, dict[str, Any]] = {}
    for record in records:
        name = str(record.get("task_name", ""))
        if name:
            latest[name] = record

    tasks: list[dict[str, Any]] = []
    for name in TASK_NAMES:
        record = latest.get(name)
        tasks.append(
            {
                "task_name": name,
                "status": (record or {}).get("status", "UNKNOWN"),
                "rows": int((record or {}).get("rows", 0) or 0),
                "cost_ms": float((record or {}).get("cost_ms", 0) or 0),
                "log_time": (record or {}).get("log_time", ""),
                "error": (record or {}).get("error", ""),
            }
        )
    return {
        "total": len(tasks),
        "succeeded": sum(1 for item in tasks if item["status"] == "SUCCESS"),
        "failed": sum(1 for item in tasks if item["status"] == "FAILED"),
        "tasks": tasks,
    }


def _resolve_runner(task_name: str) -> Callable[[str, str], Any]:
    """懒加载任务执行函数（避免应用启动即引入 pandas 等重依赖）。"""
    if task_name in TASK_RUNNERS:
        return TASK_RUNNERS[task_name]

    def _load(task: str) -> Callable[[str, str], Any]:
        if task == "extract_ods":
            from etl.jobs.extract_ods import run_extract_all

            return lambda start, end: run_extract_all(start, end, end)
        if task == "clean_dwd":
            from etl.jobs.clean_dwd import run_clean_all

            return lambda start, end: run_clean_all(end)
        if task == "dwd_wide":
            from etl.jobs.clean_dwd import run_wide_tables

            return lambda start, end: run_wide_tables(start, end, end)
        if task == "aggregate_dws":
            from etl.jobs.aggregate_dws import build_dws_daily, build_theme_marts

            return lambda start, end: {
                "dws": build_dws_daily(batch_date=end),
                **build_theme_marts(batch_date=end),
            }
        if task == "ads_indicators":
            from etl.jobs.ads_indicators import run_indicators

            return lambda start, end: run_indicators(start, end, "period", batch_date=end)
        raise BusinessError(40001, f"任务未注册执行器：{task}")

    return _load(task_name)


def trigger_task(task_name: str, start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    """手动触发任务（白名单校验 + 执行 + 汇总结果）。"""
    if task_name not in TRIGGERABLE_TASKS:
        raise BusinessError(40001, f"任务不可手动触发：{task_name}，可选 {sorted(TRIGGERABLE_TASKS)}")
    start = start_date or "2025-04-01"
    end = end_date or "2025-06-30"
    runner = _resolve_runner(task_name)
    try:
        result = runner(start, end)
    except BusinessError:
        raise
    except Exception as exc:  # noqa: BLE001 - 统一转成业务异常
        raise BusinessError(50301, f"任务 {task_name} 执行失败：{type(exc).__name__}: {exc}", status_code=503) from exc

    rows = 0
    if isinstance(result, dict):
        rows = int(sum(value for value in result.values() if isinstance(value, (int, float))))
    elif isinstance(result, (int, float)):
        rows = int(result)
    return {
        "task_name": task_name,
        "accepted": True,
        "status": "SUCCESS",
        "rows": rows,
        "message": f"任务 {task_name} 执行完成（{start} ~ {end}）",
    }


def load_quality_report(batch_date: str | None = None, report_file: Path | str | None = None) -> dict[str, Any]:
    """读取数据质量报告（默认取最新一份；可按批次日 YYYYMMDD 指定）。"""
    if report_file:
        path = Path(report_file)
    elif batch_date:
        normalized = str(batch_date).replace("-", "")[:8]
        path = _log_dir() / f"quality_report_{normalized}.json"
    else:
        candidates = sorted(_log_dir().glob("quality_report_*.json"))
        if not candidates:
            raise BusinessError(40401, "暂无数据质量报告，请先执行采集与质检任务", status_code=404)
        path = candidates[-1]

    if not path.exists():
        raise BusinessError(40401, f"质量报告不存在：{path.name}", status_code=404)

    payload = json.loads(path.read_text(encoding="utf-8"))
    summary = payload.get("summary", {})
    meta = payload.get("report_meta", {})
    return {
        "batch_date": str(meta.get("batch_date", "")),
        "score": float(summary.get("score", 0) or 0),
        "coverage_rate": float(summary.get("coverage_rate", 0) or 0),
        "total_rules": int(summary.get("total_rules", 0) or 0),
        "passed": int(summary.get("passed", 0) or 0),
        "warn": int(summary.get("warn", 0) or 0),
        "failed": int(summary.get("failed", 0) or 0),
        "blocking": bool(summary.get("blocking", False)),
        "generate_time": str(meta.get("generate_time", "")),
        "alerts": [
            {
                "rule_code": str(item.get("rule_code", "")),
                "rule_name": str(item.get("rule_name", "")),
                "table": str(item.get("table", "")),
                "level": str(item.get("level", "WARN")),
                "status": str(item.get("status", "")),
                "failed": int(item.get("failed", 0) or 0),
                "detail": str(item.get("detail", "")),
            }
            for item in payload.get("alerts", [])
        ],
    }
