"""阶段二 数据采集与整合冒烟测试。

运行：
    cd backend
    python -m tests.test_etl_smoke

覆盖点：
    1. 抽取 -> 装载 -> 清洗 -> 质检 全链路可跑通
    2. ODS / DWD 各表行数与基线一致（幂等重跑后不重复累加）
    3. 隐私字段已脱敏、费别归类与号别编码已完成标准化
    4. 由 DWD 明细可直接复算出核心指标基线（M01/M03/M10/M11/M12/M24/M32/M19）

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
    ODS_EXPECTED_ROWS,
    STAT_DAYS,
    STAT_PERIOD,
    TOTAL_BEDS,
)
from etl.config.settings import get_engine, init_ods_dwd_tables, normalize_batch_date  # noqa: E402
from etl.jobs.clean_dwd import mask_id_card, mask_name, mask_phone  # noqa: E402
from etl.jobs.clean_dwd import run_clean_all  # noqa: E402
from etl.jobs.extract_ods import run_extract_all  # noqa: E402
from etl.jobs.quality_check import generate_quality_report  # noqa: E402
from etl.scheduler.scheduler import clear_tasks, register_task, run_all as run_chain  # noqa: E402

BATCH = "2025-06-30"
_start, _end = STAT_PERIOD
_FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    icon = "PASS" if condition else "FAIL"
    print(f"  [{icon}] {name}{('  ' + detail) if detail else ''}")
    if not condition:
        _FAILED.append(name)


def scalar(sql: str) -> float:
    with get_engine().connect() as conn:
        value = conn.execute(text(sql)).scalar()
    return float(value) if value is not None else 0.0


def run_pipeline() -> None:
    """通过调度框架跑一遍全链路（与 python -m etl.jobs.run_all 等价）。"""
    clear_tasks()
    register_task("extract_ods", lambda **_: run_extract_all(_start, _end, BATCH), blocking=True)
    register_task("clean_dwd", lambda **_: run_clean_all(BATCH), requires=("extract_ods",), blocking=True)
    register_task(
        "quality_check",
        lambda **_: generate_quality_report(BATCH),
        requires=("clean_dwd",),
        blocking=False,
    )
    summary = run_chain()
    assert not summary["failed"], f"任务链存在失败：{summary['failed']}"


def main() -> int:
    print("=" * 78)
    print("阶段二 ETL 冒烟测试（临时库：%s）" % _TMP_DB)
    print("=" * 78)

    init_ods_dwd_tables()

    print("\n[1] 全链路执行（首次）")
    run_pipeline()

    print("\n[2] ODS 行数核对")
    for table, expected in ODS_EXPECTED_ROWS.items():
        actual = scalar(f"SELECT COUNT(*) FROM {table}")
        check(f"{table} = {expected}", actual == expected, f"实际 {int(actual)}")

    print("\n[3] DWD 行数核对")
    for table, expected in DWD_EXPECTED_ROWS.items():
        actual = scalar(f"SELECT COUNT(*) FROM {table}")
        check(f"{table} = {expected}", actual == expected, f"实际 {int(actual)}")

    print("\n[4] 幂等性：同批次重跑后行数不变")
    run_pipeline()
    total = sum(scalar(f"SELECT COUNT(*) FROM {t}") for t in ODS_EXPECTED_ROWS)
    check("ODS 总行数不重复累加", int(total) == sum(ODS_EXPECTED_ROWS.values()), f"实际 {int(total)}")

    print("\n[5] 清洗与脱敏效果")
    leak_name = scalar("SELECT COUNT(*) FROM dwd_outpatient_visit_detail WHERE patient_name_masked NOT LIKE '%*%'")
    leak_id = scalar("SELECT COUNT(*) FROM dwd_outpatient_visit_detail WHERE id_card_masked NOT LIKE '%*%'")
    leak_phone = scalar("SELECT COUNT(*) FROM dwd_outpatient_visit_detail WHERE phone_masked NOT LIKE '%*%'")
    check("姓名全部脱敏", leak_name == 0, f"未脱敏 {int(leak_name)} 行")
    check("身份证全部脱敏", leak_id == 0, f"未脱敏 {int(leak_id)} 行")
    check("手机号全部脱敏", leak_phone == 0, f"未脱敏 {int(leak_phone)} 行")
    check("脱敏算子示例", (mask_name("张秀兰"), mask_phone("13873577907")) == ("张**", "138****7907"))
    masked_id = mask_id_card("11018451848947609")
    check(
        "身份证脱敏保留前6后4",
        masked_id == "110184" + "*" * 7 + "7609" and len(masked_id) == 17,
        masked_id,
    )

    fee_classes = scalar("SELECT COUNT(DISTINCT fee_class) FROM dwd_charge_detail")
    check("费别归类为 4 类且无 UNKNOWN", fee_classes == 4, f"实际 {int(fee_classes)} 类")
    unknown_drg = scalar("SELECT COUNT(*) FROM dwd_inpatient_visit_detail WHERE drg_code = 'UNGROUPED'")
    check("DRG 模拟分组全部命中", unknown_drg == 0, f"未分组 {int(unknown_drg)} 行")
    dup_pk = scalar(
        "SELECT (SELECT COUNT(*)-COUNT(DISTINCT visit_id) FROM dwd_outpatient_visit_detail)"
        " + (SELECT COUNT(*)-COUNT(DISTINCT charge_id) FROM dwd_charge_detail)"
    )
    check("DWD 主键无重复", dup_pk == 0)

    print("\n[6] 由 DWD 明细复算指标基线")
    m01 = scalar(
        "SELECT COUNT(*) FROM dwd_outpatient_visit_detail "
        f"WHERE visit_date BETWEEN '{_start}' AND '{_end}'"
    )
    check("M01 门诊人次 = 9000", m01 == 9000, f"实际 {int(m01)}")

    m03 = scalar("SELECT AVG(fee_amount) FROM dwd_outpatient_visit_detail")
    check("M03 门诊次均费用 = 425.15", abs(m03 - 425.15) <= 0.01, f"实际 {m03:.2f}")

    m10 = scalar("SELECT SUM(stay_days) FROM dwd_inpatient_visit_detail")
    check("M10 实际占用总床日数 = 14317", abs(m10 - 14317) <= 0.01, f"实际 {int(m10)}")

    m08 = scalar("SELECT COUNT(*) FROM dwd_inpatient_visit_detail")
    m11 = m10 / (TOTAL_BEDS * STAT_DAYS) * 100
    check("M11 床位使用率 = 88.89%", abs(m11 - 88.89) <= 0.01, f"实际 {m11:.2f}%")

    m12 = m10 / m08
    check("M12 平均住院日 = 9.54", abs(m12 - 9.54) <= 0.01, f"实际 {m12:.2f} 天")

    m24 = scalar("SELECT SUM(rw) FROM dwd_inpatient_visit_detail") / m08
    check("M24 CMI = 1.09", abs(m24 - 1.09) <= 0.01, f"实际 {m24:.3f}")

    m32 = scalar("SELECT COUNT(*) FROM dwd_lis_report_detail WHERE result_flag = '异常'") / scalar(
        "SELECT COUNT(*) FROM dwd_lis_report_detail"
    ) * 100
    check("M32 检验阳性率 = 30.74%", abs(m32 - 30.74) <= 0.01, f"实际 {m32:.2f}%")

    fin = scalar("SELECT SUM(drug_revenue)/SUM(revenue)*100 FROM dwd_finance_daily_detail")
    check("M19 药占比（财务口径）= 30.00%", abs(fin - 30.00) <= 0.01, f"实际 {fin:.2f}%")

    m16 = scalar("SELECT SUM(amount) FROM dwd_charge_detail")
    check("M16 医疗收入合计 = 44,260,283.80", abs(m16 - 44260283.80) <= 0.01, f"实际 {m16:,.2f} 元")

    print("\n[7] 质量报告与告警")
    report = generate_quality_report(BATCH)
    summary = report["summary"]
    check("规则总数 ≥ 20 条", summary["total_rules"] >= 20, f"实际 {summary['total_rules']} 条")
    check("无阻断级失败", not summary["blocking"])
    check("字段覆盖率 = 100%", summary["coverage_rate"] == 100.0, f"实际 {summary['coverage_rate']}%")
    check("已产出告警清单", len(report["alerts"]) >= 1, f"{len(report['alerts'])} 条告警（预期含窗口截断波动）")

    print("\n" + "=" * 78)
    if _FAILED:
        print(f"测试失败 {len(_FAILED)} 项：{_FAILED}")
        return 1
    print("全部断言通过 ✔  阶段二采集与整合链路可用")
    return 0


if __name__ == "__main__":
    sys.exit(main())
