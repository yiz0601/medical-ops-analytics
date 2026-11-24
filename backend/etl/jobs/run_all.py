"""采集总入口（阶段二 · 步骤 2-4）。

用法：
    cd backend
    python -m etl.jobs.run_all --start 2025-04-01 --end 2025-06-30
    python -m etl.jobs.run_all --batch-date 2025-06-30 --skip-quality

执行链路（由 etl.scheduler.scheduler 编排）：
    extract_ods（阻断） -> clean_dwd（阻断） -> quality_check（阻断级规则失败即中止并告警）

数据库连接优先级见 etl.config.settings.get_db_url()；本地无 MySQL 时自动回退 SQLite，
便于在开发机上完成"抽取-清洗-质检"全链路冒烟验证。
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from etl.config.settings import (
    DEFAULT_BATCH_DATE,
    STAT_PERIOD_END,
    STAT_PERIOD_START,
    get_db_url,
    init_ods_dwd_tables,
)
from etl.jobs.ads_indicators import reconcile_indicators, run_indicators
from etl.jobs.aggregate_dws import build_dws_daily, build_theme_marts
from etl.jobs.clean_dwd import run_clean_all, run_wide_tables
from etl.jobs.extract_ods import run_extract_all, verify_ods_rows
from etl.jobs.init_dim import init_dim
from etl.jobs.quality_check import generate_quality_report
from etl.scheduler.scheduler import clear_tasks, list_tasks
from etl.scheduler.scheduler import register_task
from etl.scheduler.scheduler import run_all as run_chain


def build_chain(
    start_date: str,
    end_date: str,
    batch_date: str,
    *,
    with_quality: bool = True,
    with_ads: bool = True,
) -> None:
    """把七个阶段的任务注册到调度框架（依赖关系由 requires 声明）。

    链路：init_dim → extract_ods → clean_dwd → quality_check → dwd_wide
          → aggregate_dws → ads_indicators → indicator_reconcile
    """
    clear_tasks()
    register_task(
        "init_dim",
        lambda **_: init_dim(),
        blocking=True,
        max_retry=2,
        remark="公共维表全量刷新（科室/日期/病种/收费类别/DRG/号别）",
    )
    register_task(
        "extract_ods",
        lambda **_: run_extract_all(start_date, end_date, batch_date),
        requires=("init_dim",),
        blocking=True,
        max_retry=3,
        remark="多源采集并幂等装载 ODS 贴源层",
    )
    register_task(
        "clean_dwd",
        lambda **_: run_clean_all(batch_date),
        requires=("extract_ods",),
        blocking=True,
        max_retry=2,
        remark="ODS 清洗、脱敏、标准编码后写入 DWD 明细层",
    )
    if with_quality:
        register_task(
            "quality_check",
            lambda **_: generate_quality_report(batch_date, raise_on_block=True),
            requires=("clean_dwd",),
            blocking=True,
            max_retry=1,
            remark="28 条质量规则校验，产出质量报告；BLOCK 失败阻断下游并推送站内信告警",
        )
    register_task(
        "dwd_wide",
        lambda **_: run_wide_tables(start_date, end_date, batch_date),
        requires=("clean_dwd", "init_dim"),
        blocking=True,
        max_retry=2,
        remark="关联维表构建就诊/收费明细宽表（关联命中率 100%）",
    )
    register_task(
        "aggregate_dws",
        lambda **_: {
            **{"dws_dept_daily": build_dws_daily(batch_date=batch_date)},
            **build_theme_marts(batch_date=batch_date),
        },
        requires=("dwd_wide",),
        blocking=True,
        max_retry=2,
        remark="科室×日期基础度量汇总 + 8 大主题集市",
    )
    if with_ads:
        register_task(
            "ads_indicators",
            lambda **_: {
                "month": run_indicators(start_date, end_date, "month", batch_date=batch_date)["rows"],
                "period": run_indicators(start_date, end_date, "period", batch_date=batch_date)["rows"],
            },
            requires=("aggregate_dws",),
            blocking=True,
            max_retry=1,
            remark="33 项指标批量计算写入 ads_indicator_result（月 + 全期）",
        )
        def _run_reconcile(_start: str = start_date, _end: str = end_date) -> dict[str, int]:
            report = reconcile_indicators(_start, _end, granularity="period")
            return {
                "sampled": report["summary"]["sampled"],
                "passed": report["summary"]["passed"],
            }

        register_task(
            "indicator_reconcile",
            lambda **_: _run_reconcile(),
            requires=("ads_indicators",),
            blocking=False,
            max_retry=1,
            remark="抽样 10 项指标手工 SQL 复算对账（误差应为 0）",
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="etl.jobs.run_all",
        description="医疗运营数据主题分析平台 —— 数据采集与整合总入口",
    )
    parser.add_argument("--start", default=STAT_PERIOD_START, help=f"统计期开始日期（默认 {STAT_PERIOD_START}）")
    parser.add_argument("--end", default=STAT_PERIOD_END, help=f"统计期结束日期（默认 {STAT_PERIOD_END}）")
    parser.add_argument("--batch-date", default=DEFAULT_BATCH_DATE, help=f"批次业务日期（默认 {DEFAULT_BATCH_DATE}）")
    parser.add_argument("--skip-quality", action="store_true", help="跳过质量校验阶段")
    parser.add_argument("--skip-ads", action="store_true", help="跳过指标计算与对账阶段")
    parser.add_argument("--only-extract", action="store_true", help="只执行采集阶段")
    parser.add_argument("--verify", action="store_true", help="仅核对 ODS 行数与基线是否一致")
    parser.add_argument("--list-tasks", action="store_true", help="打印任务链后退出")
    args = parser.parse_args(argv)

    print("=" * 78)
    print("医疗运营数据主题分析平台 · 数据采集与整合（阶段二）")
    print(f"数据库：{get_db_url().split('@')[-1]}")
    print(f"统计期：{args.start} ~ {args.end}    批次日期：{args.batch_date}")
    print("=" * 78)

    if args.verify:
        rows = verify_ods_rows(args.batch_date)
        ok = all(r["ok"] for r in rows)
        for r in rows:
            print(f"  [{'OK  ' if r['ok'] else 'FAIL'}] {r['table']:<28} 期望 {r['expected']:>6} / 实际 {r['actual']:>6}")
        return 0 if ok else 1

    init_ods_dwd_tables()
    build_chain(
        args.start,
        args.end,
        args.batch_date,
        with_quality=not (args.skip_quality or args.only_extract),
        with_ads=not (args.skip_ads or args.only_extract),
    )

    if args.list_tasks:
        for t in list_tasks():
            print(f"  {t['task_name']:<18} requires={t['requires']} retry={t['max_retry']} blocking={t['blocking']}")
        return 0

    # 只跑采集阶段时，任务链仅保留 init_dim 与 extract_ods
    tasks = ["init_dim", "extract_ods"] if args.only_extract else None
    summary = run_chain(tasks)

    print("\n" + "-" * 78)
    print("[核对] ODS 行数与基线：")
    rows = verify_ods_rows(args.batch_date)
    for r in rows:
        print(f"  [{'OK  ' if r['ok'] else 'FAIL'}] {r['table']:<28} 期望 {r['expected']:>6} / 实际 {r['actual']:>6}")

    print("[核对] 分层落地行数：")
    from sqlalchemy import text as _text

    from etl.config.settings import get_engine as _get_engine

    layering = [
        ("DIM", "dim_department"),
        ("DIM", "dim_date"),
        ("ODS", "ods_hr_staff"),
        ("DWD", "dwd_visit_detail"),
        ("DWD", "dwd_charge_detail"),
        ("DWD", "dwd_hr_staff_detail"),
        ("DWS", "dws_dept_daily"),
        ("ADS", "ads_outpatient_theme"),
        ("ADS", "ads_income_theme"),
        ("ADS", "ads_drg_theme"),
        ("ADS", "ads_indicator_result"),
    ]
    with _get_engine().connect() as conn:
        for layer, table in layering:
            try:
                cnt = conn.execute(_text(f"SELECT COUNT(*) FROM {table}")).scalar()
                print(f"  [{layer}] {table:<26} {int(cnt):>7} 行")
            except Exception as exc:  # noqa: BLE001 - 表未创建时仅提示
                print(f"  [{layer}] {table:<26} 未就绪（{type(exc).__name__}）")

    failed = summary.get("failed") or []
    print("-" * 78)
    if failed:
        print(f"[结果] 存在失败任务：{failed}，请检查 backend/etl/logs/task_run.log")
        return 1
    chain_desc = (
        "采集阶段" if args.only_extract
        else "采集 -> 清洗 -> 质检 -> DWD 宽表 -> DWS/集市（未含指标）" if args.skip_ads
        else "采集 -> 清洗 -> 质检 -> DWD 宽表 -> DWS/集市 -> 指标计算与对账"
    )
    print(f"[结果] {chain_desc} 执行成功")
    return 0


if __name__ == "__main__":
    sys.exit(main())
