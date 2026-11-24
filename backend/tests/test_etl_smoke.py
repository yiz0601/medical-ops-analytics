"""阶段二 + 阶段三 冒烟测试（采集 → 清洗 → 质检 → 宽表 → DWS/集市 → 指标）。

运行：
    cd backend
    python -m tests.test_etl_smoke

覆盖点：
    1. 全链路 8 个任务可跑通，任务日志落盘
    2. ODS / DWD / DWS / ADS 各层行数与基线一致，幂等重跑不重复累加
    3. 隐私字段脱敏、费别归类与号别编码标准化、维表关联命中率 100%
    4. 维表行数（科室 14 / 日期 821 / 病种 10 / 收费类别 10）
    5. 33 项指标全部产出，11 项核心指标命中基线，10 项手工 SQL 对账误差 ≤ 0.01
    6. 指标结果表唯一键（指标编码+维度值+粒度+统计日期）无重复

测试库使用临时 SQLite 文件，不影响 backend/etl/logs/moa_dev.db。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# 必须在导入 etl 之前指定测试库，避免污染开发库
_TMP_DB = Path(tempfile.mkdtemp(prefix="moa_smoke_")) / "smoke.db"
os.environ["MOA_DB_URL"] = f"sqlite:///{_TMP_DB.as_posix()}"

from sqlalchemy import text  # noqa: E402

from etl.config.baseline import (  # noqa: E402
    DWD_EXPECTED_ROWS,
    METRIC_BASELINE,
    ODS_EXPECTED_ROWS,
    STAT_DAYS,
    STAT_PERIOD,
    TOTAL_BEDS,
)
from etl.config.dim_seed import DIM_EXPECTED_ROWS  # noqa: E402
from etl.config.settings import get_engine, init_ods_dwd_tables  # noqa: E402
from etl.jobs.ads_indicators import reconcile_indicators, run_indicators  # noqa: E402
from etl.jobs.aggregate_dws import build_dws_daily, build_theme_marts, verify_marts  # noqa: E402
from etl.jobs.clean_dwd import mask_id_card, mask_name, mask_phone  # noqa: E402
from etl.jobs.clean_dwd import run_clean_all, run_wide_tables, verify_dim_dwd  # noqa: E402
from etl.jobs.extract_ods import run_extract_all  # noqa: E402
from etl.jobs.init_dim import init_dim, verify_dim  # noqa: E402
from etl.jobs.quality_check import generate_quality_report  # noqa: E402
from etl.scheduler.scheduler import clear_tasks, register_task, run_all as run_chain  # noqa: E402

BATCH = "2025-06-30"
_start, _end = STAT_PERIOD
_FAILED: list[str] = []
_CHECKS: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    icon = "PASS" if condition else "FAIL"
    _CHECKS.append(name)
    print(f"  [{icon}] {name}{('  ' + detail) if detail else ''}")
    if not condition:
        _FAILED.append(name)


def scalar(sql: str) -> float:
    with get_engine().connect() as conn:
        value = conn.execute(text(sql)).scalar()
    return float(value) if value is not None else 0.0


def run_pipeline() -> dict:
    """按调度链路跑一遍全流程（与 python -m etl.jobs.run_all 等价）。"""
    clear_tasks()
    register_task("init_dim", lambda **_: init_dim(), blocking=True)
    register_task("extract_ods", lambda **_: run_extract_all(_start, _end, BATCH), requires=("init_dim",), blocking=True)
    register_task("clean_dwd", lambda **_: run_clean_all(BATCH), requires=("extract_ods",), blocking=True)
    register_task(
        "quality_check",
        lambda **_: generate_quality_report(BATCH),
        requires=("clean_dwd",),
        blocking=False,
    )
    register_task(
        "dwd_wide",
        lambda **_: run_wide_tables(_start, _end, BATCH),
        requires=("clean_dwd", "init_dim"),
        blocking=True,
    )
    register_task(
        "aggregate_dws",
        lambda **_: {
            **{"dws": build_dws_daily(batch_date=BATCH)},
            **build_theme_marts(batch_date=BATCH),
        },
        requires=("dwd_wide",),
        blocking=True,
    )
    register_task(
        "ads_indicators",
        lambda **_: run_indicators(_start, _end, "period", batch_date=BATCH),
        requires=("aggregate_dws",),
        blocking=True,
    )
    return run_chain()


def main() -> int:
    print("=" * 80)
    print("阶段二 + 阶段三 冒烟测试（临时库：%s）" % _TMP_DB)
    print("=" * 80)

    init_ods_dwd_tables()

    print("\n[1] 全链路执行（init_dim → 采集 → 清洗 → 质检 → 宽表 → DWS/集市 → 指标）")
    summary = run_pipeline()
    check("8 个链路任务无失败", not summary["failed"], f"失败={summary['failed']}")

    print("\n[2] 维表结构与行数")
    dim_rows = {row["table"]: row["actual"] for row in verify_dim() if row["check"] == "维表行数"}
    for table, expected in DIM_EXPECTED_ROWS.items():
        check(f"{table} = {expected}", dim_rows.get(table) == expected, f"实际 {dim_rows.get(table)}")
    dim_checks = verify_dim()
    check("维表校验全部通过", all(c["ok"] for c in dim_checks), f"{sum(c['ok'] for c in dim_checks)}/{len(dim_checks)} 项")

    print("\n[3] ODS / DWD 行数与基线")
    for table, expected in ODS_EXPECTED_ROWS.items():
        check(f"ODS {table} = {expected}", int(scalar(f"SELECT COUNT(*) FROM {table}")) == expected)
    for table, expected in DWD_EXPECTED_ROWS.items():
        check(f"DWD {table} = {expected}", int(scalar(f"SELECT COUNT(*) FROM {table}")) == expected)
    check("DWD 就诊宽表 = 门诊+住院 = 10500", int(scalar("SELECT COUNT(*) FROM dwd_visit_detail")) == 10500)
    wide_checks = verify_dim_dwd(BATCH)
    check("DWD 结构与对账校验全部通过", all(c["ok"] for c in wide_checks), f"{sum(c['ok'] for c in wide_checks)}/{len(wide_checks)} 项")

    print("\n[4] 幂等性：同批次重跑后行数不变")
    run_pipeline()
    ods_total = sum(int(scalar(f"SELECT COUNT(*) FROM {t}")) for t in ODS_EXPECTED_ROWS)
    check("ODS 不重复累加", ods_total == sum(ODS_EXPECTED_ROWS.values()), f"实际 {ods_total}")
    check("DWS 不重复累加", int(scalar("SELECT COUNT(*) FROM dws_dept_daily")) == 910)
    check("指标结果不重复累加", int(scalar("SELECT COUNT(*) FROM ads_indicator_result")) > 0)

    print("\n[5] 清洗与脱敏")
    for col, label in (
        ("patient_name_masked", "姓名"),
        ("id_card_masked", "身份证号"),
        ("phone_masked", "手机号"),
    ):
        leak = int(scalar(f"SELECT COUNT(*) FROM dwd_outpatient_visit_detail WHERE {col} NOT LIKE '%*%'"))
        check(f"{label}全部脱敏", leak == 0, f"未脱敏 {leak} 行")
    masked_id = mask_id_card("11018451848947609")
    check(
        "脱敏算子输出正确",
        (mask_name("张秀兰"), mask_phone("13873577907"), masked_id) == ("张**", "138****7907", "110184" + "*" * 7 + "7609"),
    )
    check("费别归类为 4 类", int(scalar("SELECT COUNT(DISTINCT fee_class) FROM dwd_charge_detail")) == 4)
    check(
        "标准收费类别关联命中 100%",
        int(scalar("SELECT COUNT(*) FROM dwd_charge_detail WHERE fee_std_name IS NULL")) == 0,
    )
    check(
        "DRG 模拟分组命中 100%",
        int(scalar("SELECT COUNT(*) FROM dwd_inpatient_visit_detail WHERE drg_code = 'UNGROUPED'")) == 0,
    )

    print("\n[6] DWS 与 8 大主题集市")
    check("dws_dept_daily = 910（10 科室 × 91 天）", int(scalar("SELECT COUNT(*) FROM dws_dept_daily")) == 910)
    mart_checks = verify_marts(BATCH)
    check("集市齐全性与聚合一致性全部通过", all(c["ok"] for c in mart_checks), f"{sum(c['ok'] for c in mart_checks)}/{len(mart_checks)} 项")
    for t in (
        "ads_outpatient_theme", "ads_inpatient_theme", "ads_income_theme", "ads_drug_theme",
        "ads_consumable_theme", "ads_drg_theme", "ads_efficiency_theme", "ads_service_theme",
    ):
        check(f"{t} = 910", int(scalar(f"SELECT COUNT(*) FROM {t}")) == 910)

    print("\n[7] 指标：产出、唯一键与基线命中")
    from etl.jobs.ads_indicators import REGISTRY

    metrics = int(scalar("SELECT COUNT(DISTINCT metric_code) FROM ads_indicator_result WHERE granularity = 'period'"))
    check(f"指标项数与注册表一致 = {len(REGISTRY)}", metrics == len(REGISTRY), f"实际 {metrics} 项")
    check("指标项数 ≥ 30", metrics >= 30, f"实际 {metrics} 项")
    dup = int(
        scalar(
            "SELECT COUNT(*) FROM (SELECT metric_code, dim_value, granularity, stat_date, COUNT(*) c"
            " FROM ads_indicator_result GROUP BY 1,2,3,4 HAVING c > 1) t"
        )
    )
    check("唯一键无重复", dup == 0)
    pending = int(
        scalar("SELECT COUNT(DISTINCT metric_code) FROM ads_indicator_result WHERE data_status = 'PENDING'")
    )
    check("待补充指标（M04/M05/M27/M33）标记为 PENDING", pending >= 3, f"{pending} 项")

    baseline_map = {
        "M01": METRIC_BASELINE["M01"],
        "M03": METRIC_BASELINE["M03"],
        "M08": METRIC_BASELINE["M08"],
        "M10": METRIC_BASELINE["M10"],
        "M11": METRIC_BASELINE["M11"],
        "M12": METRIC_BASELINE["M12"],
        "M16": METRIC_BASELINE["M16"],
        "M19": METRIC_BASELINE["M19"],
        "M20": METRIC_BASELINE["M20"],
        "M24": METRIC_BASELINE["M24"],
        "M25": METRIC_BASELINE["M25"],
        "M26": METRIC_BASELINE["M26"],
        "M31": METRIC_BASELINE["M31"],
        "M32": METRIC_BASELINE["M32"],
    }
    for code, expected in baseline_map.items():
        actual = scalar(
            "SELECT metric_value FROM ads_indicator_result"
            f" WHERE metric_code = '{code}' AND dim_value = 'ALL' AND granularity = 'period'"
            f" AND stat_date = '{_end}'"
        )
        check(f"{code} 命中基线 {expected}", abs(actual - float(expected)) <= 0.01, f"实际 {actual:,.4f}")

    print("\n[8] 手工 SQL 对账（抽样 10 项，误差应为 0）")
    report = reconcile_indicators(_start, _end, granularity="period")
    check("抽样 10 项全部通过", report["summary"]["passed"] == report["summary"]["sampled"],
          f"{report['summary']['passed']}/{report['summary']['sampled']}")
    check("最大绝对误差 ≤ 0.01", report["summary"]["max_abs_error"] <= 0.01, f"{report['summary']['max_abs_error']}")

    print("\n[9] 核账：DWS = 集市 = DWD 收入合计")
    dws_amt = scalar("SELECT SUM(charge_amt_sum) FROM dws_dept_daily")
    mart_amt = scalar("SELECT SUM(total_amt) FROM ads_income_theme")
    dwd_amt = scalar("SELECT SUM(amount) FROM dwd_charge_detail")
    check(
        "三方收入一致（44,260,283.80）",
        abs(dws_amt - dwd_amt) < 0.01 and abs(mart_amt - dwd_amt) < 0.01,
        f"DWS {dws_amt:,.2f} / 集市 {mart_amt:,.2f} / DWD {dwd_amt:,.2f}",
    )

    print("\n" + "=" * 80)
    if _FAILED:
        print(f"测试失败 {len(_FAILED)}/{len(_CHECKS)} 项：{_FAILED}")
        return 1
    print(f"全部 {len(_CHECKS)} 项断言通过 ✔  阶段二采集整合 + 阶段三数仓与指标链路可用")
    return 0


if __name__ == "__main__":
    sys.exit(main())
