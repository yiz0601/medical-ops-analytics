"""试运行检查与指标闭环（阶段七 · 步骤 4）。

    collect_trial_metrics(start, end)  汇总试运行期间的任务成功率、对账结果与质量告警，
                                       按问题逐项登记（含级别与闭环状态），输出试运行报告数据
    export_trial_report(...)           把结果落盘为 JSON（供《试运行报告》引用）

数据来源：ETL 任务日志、指标对账记录、质量报告（均位于 backend/etl/logs/）。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from etl.config.settings import LOG_DIR

TRIAL_LOG_DIR = LOG_DIR


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _read_task_log(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _issue_level(rule_code: str, level: str) -> str:
    """问题定级：阻断级规则为 P0，告警为 P1，其余提示为 P2。"""
    if level == "BLOCK":
        return "P0"
    if rule_code.startswith("QR-DQ"):
        return "P1"
    return "P2"


def collect_trial_metrics(
    start_date: str,
    end_date: str,
    *,
    log_dir: Path | str | None = None,
) -> dict[str, Any]:
    """汇总试运行指标与问题清单。"""
    base = Path(log_dir) if log_dir else TRIAL_LOG_DIR

    # 1) 任务成功率
    task_records = _read_task_log(base / "task_run.log")
    total_runs = len(task_records)
    success_runs = sum(1 for item in task_records if item.get("status") == "SUCCESS")
    failed_runs = total_runs - success_runs
    by_task: dict[str, dict[str, int]] = {}
    for item in task_records:
        name = str(item.get("task_name", ""))
        stat = by_task.setdefault(name, {"total": 0, "success": 0, "failed": 0})
        stat["total"] += 1
        if item.get("status") == "SUCCESS":
            stat["success"] += 1
        else:
            stat["failed"] += 1

    # 2) 指标对账结果（取区间内最新的对账记录）
    reconcile_files = sorted(base.glob("indicator_reconcile_*.json"))
    reconcile = _read_json(reconcile_files[-1]) if reconcile_files else None

    # 3) 质量报告（取最新一份）
    quality_files = sorted(base.glob("quality_report_*.json"))
    quality = _read_json(quality_files[-1]) if quality_files else None

    # 4) 问题登记：质量告警 + 任务失败 + 对账偏差
    issues: list[dict[str, Any]] = []
    if quality:
        for alert in quality.get("alerts", []):
            issues.append(
                {
                    "source": "数据质量",
                    "rule_code": alert.get("rule_code", ""),
                    "object": alert.get("table", ""),
                    "level": _issue_level(str(alert.get("rule_code", "")), str(alert.get("level", ""))),
                    "detail": alert.get("detail", ""),
                    "status": "已登记-待跟踪" if alert.get("level") != "BLOCK" else "阻断-需处理",
                }
            )
    for item in task_records:
        if item.get("status") == "FAILED":
            issues.append(
                {
                    "source": "任务日志",
                    "rule_code": str(item.get("task_name", "")),
                    "object": str(item.get("task_name", "")),
                    "level": "P0",
                    "detail": str(item.get("error", ""))[:200],
                    "status": "已修复并重跑成功" if failed_runs == 0 else "待处理",
                }
            )
    if reconcile:
        summary = reconcile.get("summary", {})
        if not summary.get("all_zero_error", False):
            issues.append(
                {
                    "source": "指标对账",
                    "rule_code": "RECONCILE",
                    "object": "ads_indicator_result",
                    "level": "P0",
                    "detail": f"最大绝对误差 {summary.get('max_abs_error')}",
                    "status": "待处理",
                }
            )

    # 5) 指标闭环：抽样 10 项
    reconcile_summary = (reconcile or {}).get("summary", {})
    return {
        "report_meta": {
            "stage": "阶段七 试运行",
            "period": [start_date, end_date],
            "generate_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "log_dir": str(base),
        },
        "task_summary": {
            "total_runs": total_runs,
            "success_runs": success_runs,
            "failed_runs": failed_runs,
            "success_rate": round(success_runs / total_runs * 100, 2) if total_runs else 0.0,
            "by_task": by_task,
        },
        "reconcile_summary": {
            "sampled": reconcile_summary.get("sampled", 0),
            "passed": reconcile_summary.get("passed", 0),
            "failed": reconcile_summary.get("failed", 0),
            "max_abs_error": reconcile_summary.get("max_abs_error"),
            "all_zero_error": reconcile_summary.get("all_zero_error"),
            "record_file": reconcile_files[-1].name if reconcile_files else None,
        },
        "quality_summary": {
            "batch_date": (quality or {}).get("report_meta", {}).get("batch_date"),
            "score": (quality or {}).get("summary", {}).get("score"),
            "coverage_rate": (quality or {}).get("summary", {}).get("coverage_rate"),
            "total_rules": (quality or {}).get("summary", {}).get("total_rules"),
            "alerts": len((quality or {}).get("alerts", [])),
            "report_file": quality_files[-1].name if quality_files else None,
        },
        "issues": issues,
        "issue_stats": {
            "total": len(issues),
            "p0": sum(1 for item in issues if item["level"] == "P0"),
            "p1": sum(1 for item in issues if item["level"] == "P1"),
            "p2": sum(1 for item in issues if item["level"] == "P2"),
        },
    }


def export_trial_report(start_date: str, end_date: str, *, log_dir: Path | str | None = None) -> Path:
    """生成并落盘试运行报告数据（JSON），返回文件路径。"""
    report = collect_trial_metrics(start_date, end_date, log_dir=log_dir)
    base = Path(log_dir) if log_dir else TRIAL_LOG_DIR
    base.mkdir(parents=True, exist_ok=True)
    target = base / f"trial_report_{end_date.replace('-', '')}.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[试运行] 报告已生成：{target}")
    return target


if __name__ == "__main__":  # 手工执行：python -m etl.jobs.trial_check
    from etl.config.baseline import STAT_PERIOD

    summary = collect_trial_metrics(*STAT_PERIOD)
    print(json.dumps({"task_summary": summary["task_summary"], "issue_stats": summary["issue_stats"]}, ensure_ascii=False, indent=2))
    export_trial_report(*STAT_PERIOD)
