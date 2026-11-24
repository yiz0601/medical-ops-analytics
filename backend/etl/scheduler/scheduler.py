"""ETL 调度框架（阶段二 · 步骤 2-3）。

提供最小可用的任务注册、重试执行、依赖编排、日志落盘与定时调度能力：

    register_task(name, func, ...)   注册任务（可声明依赖与重试次数）
    run_task(name, max_retry=3)      执行单个任务（失败自动重试，记录耗时与行数）
    run_all()                        按注册顺序（尊重依赖）串跑全链路
    setup_schedule()                 启动每日定时调度（APScheduler，未安装则仅打印计划）
    log_write(name, status, rows, cost_ms)  采集日志落盘 backend/etl/logs/task_run.log

后续可平滑替换为 Airflow / DolphinScheduler：任务函数签名保持不变。
"""

from __future__ import annotations

import json
import time
import traceback
from collections import OrderedDict
from datetime import datetime
from typing import Any, Callable

from etl.config.settings import TASK_LOG_FILE

# 任务注册表：name -> 任务定义（有序，保持注册顺序即执行顺序）
_REGISTRY: "OrderedDict[str, dict[str, Any]]" = OrderedDict()


# ---------------------------------------------------------------- 步骤 2-3：注册与日志
def register_task(
    name: str,
    func: Callable[..., Any],
    *,
    requires: tuple[str, ...] = (),
    max_retry: int = 3,
    blocking: bool = True,
    params: dict[str, Any] | None = None,
    remark: str = "",
) -> dict[str, Any]:
    """注册一个 ETL 任务。

    参数
    ----
    name       任务名（如 extract_ods / clean_dwd / quality_check）
    func       任务函数，返回值建议为 {表名: 行数} 或 int（用于统计处理行数）
    requires   依赖的任务名；依赖未成功时本任务会被跳过
    max_retry  失败重试次数（含首次执行）
    blocking   失败后是否阻断后续任务（True=阻断下游）
    params     固定参数，运行时参数会覆盖同名项
    """
    if not callable(func):
        raise TypeError(f"任务函数不可调用：{name}")
    _REGISTRY[name] = {
        "task_name": name,
        "func": func,
        "requires": tuple(requires),
        "max_retry": max(1, int(max_retry)),
        "blocking": bool(blocking),
        "params": dict(params or {}),
        "remark": remark,
    }
    return _REGISTRY[name]


def list_tasks() -> list[dict[str, Any]]:
    """返回已注册任务清单（按执行顺序）。"""
    return [
        {
            "task_name": t["task_name"],
            "requires": t["requires"],
            "max_retry": t["max_retry"],
            "blocking": t["blocking"],
            "remark": t["remark"],
        }
        for t in _REGISTRY.values()
    ]


def clear_tasks() -> None:
    """清空任务注册表（测试用）。"""
    _REGISTRY.clear()


def log_write(
    name: str,
    status: str,
    rows: int,
    cost_ms: float,
    error: str | None = None,
) -> dict[str, Any]:
    """采集/加工日志落盘（JSON Lines）并打印一行摘要。"""
    record = {
        "task_name": name,
        "status": status,          # SUCCESS / FAILED / SKIPPED
        "rows": int(rows or 0),
        "cost_ms": round(float(cost_ms or 0), 2),
        "error": error or "",
        "log_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    TASK_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with TASK_LOG_FILE.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(record, ensure_ascii=False) + "\n")
    icon = {"SUCCESS": "✔", "FAILED": "✘", "SKIPPED": "→"}.get(status, "·")
    tail = f"  error={error}" if error else ""
    _safe_print(
        f"  {icon} [{record['log_time']}] {name:<14} {status:<8} "
        f"rows={record['rows']:>6} cost={record['cost_ms']:>9.1f}ms{tail}"
    )
    return record


def _safe_print(text: str) -> None:
    """跨平台安全打印：控制台编码不支持符号（如 Windows GBK 下的 ✔/✘）时降级为 ASCII。"""
    try:
        print(text)
    except UnicodeEncodeError:
        fallback = text.replace("✔", "[OK]").replace("✘", "[FAIL]").replace("→", "->").replace("·", ".")
        print(fallback.encode("ascii", errors="replace").decode("ascii"))


# ---------------------------------------------------------------- 步骤 2-3：执行
def _rows_of(result: Any) -> int:
    """从任务返回值中提取处理行数。"""
    if isinstance(result, dict):
        return int(sum(v for v in result.values() if isinstance(v, (int, float))))
    if isinstance(result, (int, float)):
        return int(result)
    return 0


def run_task(
    name: str,
    max_retry: int | None = None,
    **params: Any,
) -> dict[str, Any]:
    """执行单个任务，失败按 max_retry 自动重试，返回执行记录。"""
    if name not in _REGISTRY:
        raise KeyError(f"任务未注册：{name}，已注册：{', '.join(_REGISTRY)}")
    task = _REGISTRY[name]
    attempts = max(1, int(max_retry or task["max_retry"]))
    merged: dict[str, Any] = {**task["params"], **params}

    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        started = time.perf_counter()
        try:
            result = task["func"](**merged)
            cost_ms = (time.perf_counter() - started) * 1000
            record = log_write(name, "SUCCESS", _rows_of(result), cost_ms)
            record.update({"attempts": attempt, "result": result})
            return record
        except Exception as exc:  # noqa: BLE001 - 统一走重试与日志
            last_error = exc
            cost_ms = (time.perf_counter() - started) * 1000
            detail = f"{type(exc).__name__}: {exc}"
            log_write(name, "FAILED", 0, cost_ms, error=f"第 {attempt}/{attempts} 次失败 {detail}")
            if attempt < attempts:
                time.sleep(min(2 ** attempt, 5))  # 指数退避，最长 5 秒

    assert last_error is not None
    raise RuntimeError(f"任务 {name} 重试 {attempts} 次后仍失败：{last_error}") from last_error


def run_all(task_names: list[str] | None = None, **params: Any) -> dict[str, Any]:
    """按注册顺序串跑任务链路（尊重 requires 依赖），返回执行摘要。"""
    names = list(task_names or list(_REGISTRY.keys()))
    summary: dict[str, Any] = {}
    started = time.perf_counter()

    print(f"[调度] 开始执行 {len(names)} 个任务：{' -> '.join(names)}")
    for name in names:
        if name not in _REGISTRY:
            summary[name] = {"task_name": name, "status": "SKIPPED", "error": "任务未注册"}
            print(f"  → {name:<14} SKIPPED  任务未注册")
            continue

        missing = [d for d in _REGISTRY[name]["requires"] if summary.get(d, {}).get("status") != "SUCCESS"]
        if missing:
            summary[name] = log_write(name, "SKIPPED", 0, 0.0, error=f"依赖未成功：{missing}")
            continue

        try:
            summary[name] = run_task(name, **params)
        except RuntimeError as exc:
            summary[name] = {"task_name": name, "status": "FAILED", "error": str(exc)}
            if _REGISTRY[name]["blocking"]:
                print(f"[调度] 任务 {name} 失败且为阻断型，终止后续任务")
                break

    total_ms = (time.perf_counter() - started) * 1000
    failed = [k for k, v in summary.items() if v.get("status") == "FAILED"]
    skipped = [k for k, v in summary.items() if v.get("status") == "SKIPPED"]
    print(
        f"[调度] 结束：成功 {sum(1 for v in summary.values() if v.get('status') == 'SUCCESS')}"
        f" / 失败 {len(failed)} / 跳过 {len(skipped)}，总耗时 {total_ms / 1000:.2f}s"
    )
    return {"tasks": summary, "failed": failed, "skipped": skipped, "total_cost_ms": round(total_ms, 2)}


# ---------------------------------------------------------------- 步骤 2-3：定时调度
def setup_schedule(cron: str = "0 2 * * *", task_names: list[str] | None = None) -> Any:
    """启动每日定时调度（T+1 日终批）。

    依赖 APScheduler；未安装时仅打印调度计划并返回 None，方便无依赖环境自检。
    """
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        print("[调度] 未安装 APScheduler，跳过定时调度（pip install apscheduler 后可用）")
        print(f"[调度] 计划：cron='{cron}'，任务链={task_names or list(_REGISTRY)}")
        return None

    minute, hour, day, month, day_of_week = cron.split()
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(
        lambda: run_all(task_names),
        trigger=CronTrigger(minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week),
        id="moa_daily_batch",
        name="医疗运营平台每日采集批",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    print(f"[调度] 已启动定时调度：cron='{cron}'，任务链={task_names or list(_REGISTRY)}")
    return scheduler


if __name__ == "__main__":  # 手工自检：python -m etl.scheduler.scheduler
    print("已注册任务：")
    for t in list_tasks():
        print(f"  {t['task_name']:<14} requires={t['requires']} retry={t['max_retry']} blocking={t['blocking']}")
    setup_schedule()
