"""数据质量校验与质量报告（阶段二 · 步骤 4、5）。

五类校验规则（规则可配置、结果可汇总）：

    check_null_ratio(table, columns)        关键字段空值率
    check_duplicate(table, keys)            主键/业务键唯一性
    check_value_range(table, rules)         值域校验（枚举/区间）
    check_volume_wave(table, date_column)   数据量日环比波动率（默认 ±30%）
    check_reconcile(ods_table, dwd_table)   ODS 与 DWD 行数对账

报告入口 generate_quality_report(batch_date)：汇总全部规则结果，计算质量评分与
字段覆盖率，输出告警清单（BLOCK 阻断 / WARN 告警），落盘
backend/etl/logs/quality_report_YYYYMMDD.json，并通过 `etl.jobs.alert_notify`
把告警推送到站内信表 `sys_alert`（含送达耗时与及时率）。
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Iterable, Sequence

import pandas as pd
from sqlalchemy.engine import Engine

from etl.config.loader import read_table_df
from etl.config.ods_schema import ODS_TABLES
from etl.config.dwd_schema import DWD_TABLES
from etl.config.settings import (
    LOG_DIR,
    NULL_RATIO_THRESHOLD,
    RECONCILE_TOLERANCE,
    VOLUME_WAVE_THRESHOLD,
    get_engine,
    normalize_batch_date,
)

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


class QualityBlockedError(RuntimeError):
    """质检存在 BLOCK 级规则失败：阻断下游发布并已推送站内信告警。"""

    def __init__(self, batch_date: Any, blocking_alerts: Sequence[dict[str, Any]]) -> None:
        codes = ", ".join(str(a.get("rule_code")) for a in blocking_alerts) or "-"
        super().__init__(f"批次 {batch_date} 存在阻断级质量规则失败（{codes}），已阻断下游发布并推送告警")
        self.batch_date = batch_date
        self.blocking_alerts = list(blocking_alerts)


def _rate(total: int, failed: int) -> float:
    """通过率（%）。"""
    if total <= 0:
        return 100.0
    return round((1 - failed / total) * 100, 2)


def _result(
    rule_code: str,
    rule_name: str,
    rule_type: str,
    table: str,
    total: int,
    failed: int,
    *,
    level: str = "WARN",
    detail: str = "",
    status: str | None = None,
) -> dict[str, Any]:
    """构造统一格式的规则结果。"""
    if status is None:
        status = PASS if failed == 0 else (FAIL if level == "BLOCK" else WARN)
    return {
        "rule_code": rule_code,
        "rule_name": rule_name,
        "rule_type": rule_type,
        "table": table,
        "level": level,
        "total": int(total),
        "failed": int(failed),
        "pass_rate": _rate(total, failed),
        "status": status,
        "detail": detail,
    }


# ---------------------------------------------------------------- 步骤 4-1：空值率
def check_null_ratio(
    table: str,
    columns: Sequence[str],
    threshold: float = NULL_RATIO_THRESHOLD,
    *,
    batch_date: date | str | None = None,
    engine: Engine | None = None,
    rule_code: str = "",
) -> dict[str, Any]:
    """校验关键字段空值率是否超阈值。"""
    df = read_table_df(engine or get_engine(), ODS_TABLES.get(table, DWD_TABLES.get(table)), batch_date)
    total_rows = len(df)
    offenders: list[str] = []
    failed = 0
    for col in columns:
        if col not in df.columns:
            offenders.append(f"{col}(列缺失)")
            failed += total_rows
            continue
        nulls = int(df[col].isna().sum())
        ratio = nulls / total_rows if total_rows else 0.0
        if ratio > threshold:
            offenders.append(f"{col}={nulls}行({ratio:.2%})")
            failed += nulls
    detail = "超阈值字段：" + "、".join(offenders) if offenders else f"{len(columns)} 个关键字段空值率均 ≤ {threshold:.0%}"
    return _result(rule_code, "关键字段空值率", "完整性", table, total_rows, failed, detail=detail)


# ---------------------------------------------------------------- 步骤 4-2：唯一性
def check_duplicate(
    table: str,
    keys: Sequence[str],
    *,
    batch_date: date | str | None = None,
    engine: Engine | None = None,
    rule_code: str = "",
) -> dict[str, Any]:
    """校验主键/业务键唯一性。"""
    tbl = ODS_TABLES.get(table, DWD_TABLES.get(table))
    df = read_table_df(engine or get_engine(), tbl, batch_date)
    cols = [k for k in keys if k in df.columns]
    total = len(df)
    if not cols:
        return _result(rule_code, "主键唯一性", "唯一性", table, total, 0, level="BLOCK", detail="校验字段不存在", status=FAIL)
    duplicated = int(df.duplicated(subset=cols, keep=False).sum())
    detail = f"主键 {'+'.join(cols)} 重复 {duplicated} 行" if duplicated else f"主键 {'+'.join(cols)} 无重复"
    return _result(rule_code, "主键唯一性", "唯一性", table, total, duplicated, level="BLOCK", detail=detail)


# ---------------------------------------------------------------- 步骤 4-3：值域
def check_value_range(
    table: str,
    rules: dict[str, Any],
    *,
    batch_date: date | str | None = None,
    engine: Engine | None = None,
    rule_code: str = "",
) -> dict[str, Any]:
    """值域校验。

    rules 形如：
        {"visit_type": {"type": "enum", "values": ["普通", "专家", "急诊"]},
         "age": {"type": "range", "min": 0, "max": 120}}
    """
    df = read_table_df(engine or get_engine(), ODS_TABLES.get(table, DWD_TABLES.get(table)), batch_date)
    total_rows = len(df)
    offenders: list[str] = []
    failed = 0
    for col, spec in rules.items():
        if col not in df.columns:
            offenders.append(f"{col}(列缺失)")
            failed += total_rows
            continue
        series = df[col]
        notnull = series.dropna()
        if spec.get("type") == "enum":
            allowed = set(spec.get("values") or [])
            bad = int((~notnull.isin(allowed)).sum())
            if bad:
                unexpected = sorted({str(v) for v in notnull[~notnull.isin(allowed)].unique()})[:5]
                offenders.append(f"{col}={bad}行(异常取值{unexpected})")
        else:
            numeric = pd.to_numeric(notnull, errors="coerce")
            low = spec.get("min")
            high = spec.get("max")
            bad = 0
            if low is not None:
                bad += int((numeric < low).sum())
            if high is not None:
                bad += int((numeric > high).sum())
            bad += int(numeric.isna().sum())
            if bad:
                offenders.append(f"{col}={bad}行(超出[{low},{high}])")
        failed += bad
    detail = "异常：" + "、".join(offenders) if offenders else f"{len(rules)} 个字段值域校验通过"
    return _result(rule_code, "值域校验", "值域", table, total_rows * max(len(rules), 1), failed, detail=detail)


# ---------------------------------------------------------------- 步骤 4-4：波动率
def check_volume_wave(
    table: str,
    date_column: str,
    threshold: float = VOLUME_WAVE_THRESHOLD,
    *,
    batch_date: date | str | None = None,
    engine: Engine | None = None,
    rule_code: str = "",
) -> dict[str, Any]:
    """数据量日环比波动率校验（|今日-昨日|/昨日 > threshold 视为异常）。"""
    df = read_table_df(engine or get_engine(), ODS_TABLES.get(table, DWD_TABLES.get(table)), batch_date)
    if date_column not in df.columns or df.empty:
        return _result(rule_code, "行数波动率", "一致性", table, 0, 0, detail="无日期列或无数据", status=FAIL)
    daily = pd.to_datetime(df[date_column], errors="coerce").dropna().dt.date.value_counts().sort_index()
    days = list(daily.index)
    waves: list[tuple[date, int, int, float]] = []
    for prev, cur in zip(days, days[1:]):
        prev_cnt, cur_cnt = int(daily[prev]), int(daily[cur])
        if prev_cnt <= 0:
            continue
        wave = (cur_cnt - prev_cnt) / prev_cnt
        if abs(wave) > threshold:
            waves.append((cur, cur_cnt, prev_cnt, round(wave, 4)))
    total = max(len(days) - 1, 1)
    failed = len(waves)
    if waves:
        top = sorted(waves, key=lambda x: abs(x[3]), reverse=True)[:3]
        detail = "超阈值日期：" + "、".join(f"{d}(当日{c}/前日{p},{w:+.1%})" for d, c, p, w in top)
    else:
        detail = f"日环比波动均在 ±{threshold:.0%} 内（{days[0]} ~ {days[-1]}，均值 {daily.mean():.1f}）"
    return _result(rule_code, "行数波动率", "一致性", table, total, failed, detail=detail)


# ---------------------------------------------------------------- 步骤 4-5：对账
def check_reconcile(
    ods_table: str,
    dwd_table: str,
    tolerance: float = RECONCILE_TOLERANCE,
    *,
    batch_date: date | str | None = None,
    engine: Engine | None = None,
    rule_code: str = "",
) -> dict[str, Any]:
    """ODS 与 DWD 行数对账（清洗去重后行数差异率须 ≤ tolerance）。"""
    eng = engine or get_engine()
    ods_rows = len(read_table_df(eng, ODS_TABLES[ods_table], batch_date))
    dwd_rows = len(read_table_df(eng, DWD_TABLES[dwd_table], batch_date))
    failed = abs(ods_rows - dwd_rows)
    diff_rate = failed / ods_rows if ods_rows else 0.0
    status = PASS if diff_rate <= tolerance else FAIL
    detail = f"ODS {ods_rows} 行 / DWD {dwd_rows} 行，差异 {failed} 行（{diff_rate:.2%}）"
    return _result(
        rule_code, "ODS-DWD 行数对账", "一致性", f"{ods_table}→{dwd_table}",
        ods_rows, failed, level="BLOCK", detail=detail, status=status,
    )


# ---------------------------------------------------------------- 步骤 5：质量报告
# 关键字段清单（用于覆盖率计算）
KEY_FIELDS: dict[str, list[str]] = {
    "ods_his_outpatient_visit": ["visit_id", "patient_id", "dept_code", "visit_date", "visit_type", "fee_amount"],
    "ods_his_inpatient_visit": ["visit_id", "dept_code", "admit_date", "discharge_date", "stay_days", "total_fee"],
    "ods_his_charge_detail": ["charge_id", "visit_id", "fee_date", "fee_type_code", "amount"],
    "ods_emr_record": ["record_id", "visit_id", "disease_code"],
    "ods_lis_report": ["report_id", "visit_id", "item_name", "result_text"],
    "ods_finance_excel": ["record_id", "stat_date", "dept_code", "revenue"],
    "ods_hr_staff": ["dept_code", "stat_date", "doctor_cnt", "nurse_cnt"],
}

# 已配置规则覆盖的字段（覆盖率分子）
COVERED_FIELDS: dict[str, list[str]] = {
    "ods_his_outpatient_visit": ["visit_id", "patient_id", "dept_code", "visit_date", "visit_type", "fee_amount"],
    "ods_his_inpatient_visit": ["visit_id", "dept_code", "admit_date", "discharge_date", "stay_days", "total_fee"],
    "ods_his_charge_detail": ["charge_id", "visit_id", "fee_date", "fee_type_code", "amount"],
    "ods_emr_record": ["record_id", "visit_id", "disease_code"],
    "ods_lis_report": ["report_id", "visit_id", "item_name", "result_text"],
    "ods_finance_excel": ["record_id", "stat_date", "dept_code", "revenue"],
    "ods_hr_staff": ["dept_code", "stat_date", "doctor_cnt", "nurse_cnt"],
}

GENDER_ENUM = {"type": "enum", "values": ["男", "女"]}
VISIT_TYPE_ENUM = {"type": "enum", "values": ["普通", "专家", "急诊"]}
FEE_TYPE_ENUM = {"type": "enum", "values": ["XY", "ZC", "JC", "JY", "ZL", "SS", "CL", "CW", "HL"]}
RESULT_ENUM = {"type": "enum", "values": ["阴性", "未见异常", "正常", "在参考范围内", "阳性", "偏高", "偏低", "异常"]}

RECONCILE_PAIRS = [
    ("ods_his_outpatient_visit", "dwd_outpatient_visit_detail"),
    ("ods_his_inpatient_visit", "dwd_inpatient_visit_detail"),
    ("ods_his_charge_detail", "dwd_charge_detail"),
    ("ods_emr_record", "dwd_emr_record_detail"),
    ("ods_lis_report", "dwd_lis_report_detail"),
    ("ods_finance_excel", "dwd_finance_daily_detail"),
    ("ods_hr_staff", "dwd_hr_staff_detail"),
]


def run_all_rules(batch_date: date | str | None = None, *, engine: Engine | None = None) -> list[dict[str, Any]]:
    """执行全部质量规则，返回结果列表（规则编号按 QR-DQ / QR-REC 编号）。"""
    eng = engine or get_engine()
    bd = normalize_batch_date(batch_date)
    results: list[dict[str, Any]] = []
    seq = 0

    # 1) 主键唯一性（7 张表）
    pk_map = {
        "ods_his_outpatient_visit": ["visit_id"],
        "ods_his_inpatient_visit": ["visit_id"],
        "ods_his_charge_detail": ["charge_id"],
        "ods_emr_record": ["record_id"],
        "ods_lis_report": ["report_id"],
        "ods_finance_excel": ["record_id"],
        "ods_hr_staff": ["dept_code", "stat_date"],
    }
    for table, keys in pk_map.items():
        seq += 1
        results.append(check_duplicate(table, keys, batch_date=bd, engine=eng, rule_code=f"QR-DQ-{seq:02d}"))

    # 2) 关键字段空值率（按表）
    for table, cols in KEY_FIELDS.items():
        seq += 1
        results.append(check_null_ratio(table, cols, batch_date=bd, engine=eng, rule_code=f"QR-DQ-{seq:02d}"))

    # 3) 值域校验
    seq += 1
    results.append(
        check_value_range(
            "ods_his_outpatient_visit",
            {"visit_type": VISIT_TYPE_ENUM, "gender": GENDER_ENUM,
             "age": {"type": "range", "min": 0, "max": 120},
             "fee_amount": {"type": "range", "min": 0, "max": 1_000_000}},
            batch_date=bd, engine=eng, rule_code=f"QR-DQ-{seq:02d}",
        )
    )
    seq += 1
    results.append(
        check_value_range(
            "ods_his_inpatient_visit",
            {"stay_days": {"type": "range", "min": 0, "max": 365},
             "total_fee": {"type": "range", "min": 0, "max": 10_000_000},
             "gender": GENDER_ENUM},
            batch_date=bd, engine=eng, rule_code=f"QR-DQ-{seq:02d}",
        )
    )
    seq += 1
    results.append(
        check_value_range(
            "ods_his_charge_detail",
            {"fee_type_code": FEE_TYPE_ENUM, "amount": {"type": "range", "min": 0, "max": 1_000_000}},
            batch_date=bd, engine=eng, rule_code=f"QR-DQ-{seq:02d}",
        )
    )
    seq += 1
    results.append(
        check_value_range(
            "ods_lis_report", {"result_text": RESULT_ENUM}, batch_date=bd, engine=eng, rule_code=f"QR-DQ-{seq:02d}"
        )
    )
    seq += 1
    results.append(
        check_value_range(
            "ods_finance_excel",
            {"revenue": {"type": "range", "min": 0, "max": 100_000_000},
             "drug_revenue": {"type": "range", "min": 0, "max": 100_000_000},
             "consumable_revenue": {"type": "range", "min": 0, "max": 100_000_000}},
            batch_date=bd, engine=eng, rule_code=f"QR-DQ-{seq:02d}",
        )
    )

    # 4) 行数波动率
    seq += 1
    results.append(
        check_volume_wave("ods_his_outpatient_visit", "visit_date", batch_date=bd, engine=eng, rule_code=f"QR-DQ-{seq:02d}")
    )
    seq += 1
    results.append(
        check_volume_wave(
            "ods_his_inpatient_visit", "discharge_date", batch_date=bd, engine=eng, rule_code=f"QR-DQ-{seq:02d}"
        )
    )

    # 5) ODS-DWD 对账
    for idx, (ods_table, dwd_table) in enumerate(RECONCILE_PAIRS, start=1):
        results.append(
            check_reconcile(ods_table, dwd_table, batch_date=bd, engine=eng, rule_code=f"QR-REC-{idx:02d}")
        )
    return results


def _coverage() -> tuple[float, int, int]:
    """字段覆盖率：已配置规则覆盖的关键字段数 / 关键字段总数。"""
    total = sum(len(v) for v in KEY_FIELDS.values())
    covered = sum(len(set(COVERED_FIELDS.get(t, [])) & set(KEY_FIELDS[t])) for t in KEY_FIELDS)
    return (round(covered / total * 100, 2) if total else 0.0), covered, total


def generate_quality_report(
    batch_date: date | str | None = None,
    *,
    engine: Engine | None = None,
    output_dir: str | None = None,
    notify: bool = True,
    raise_on_block: bool = False,
) -> dict[str, Any]:
    """汇总规则结果，计算评分与覆盖率，落盘 JSON；按需推送站内信告警并输出。

    * `notify=True`（默认）：把告警写入 `sys_alert` 站内信表，并在报告 `summary.notify`
      中给出送达条数与通知及时率（任务书「异常数据告警通知及时率 100%」的可核对依据）
    * `raise_on_block=True`：存在 BLOCK 级规则失败时抛出 `QualityBlockedError`，
      由调度链阻断下游发布（任务书「异常时阻断下游发布并告警」）
    """
    bd = normalize_batch_date(batch_date)
    eng = engine or get_engine()
    results = run_all_rules(bd, engine=eng)

    passed = [r for r in results if r["status"] == PASS]
    warned = [r for r in results if r["status"] == WARN]
    failed = [r for r in results if r["status"] == FAIL]
    total = len(results)
    score = round(len(passed) / total * 100, 2) if total else 0.0
    coverage, covered, key_total = _coverage()

    alerts = [
        {
            "rule_code": r["rule_code"],
            "rule_name": r["rule_name"],
            "table": r["table"],
            "level": r["level"],
            "status": r["status"],
            "failed": r["failed"],
            "detail": r["detail"],
        }
        for r in results
        if r["status"] != PASS
    ]
    # 告警分级：BLOCK 优先级高于 WARN，再按失败行数排序
    alerts.sort(key=lambda a: (a["level"] != "BLOCK", a["status"] != "FAIL", -a["failed"]))

    report = {
        "report_meta": {
            "project": "医疗运营数据主题分析平台",
            "stage": "阶段二 数据采集与整合",
            "batch_date": str(bd),
            "generate_time": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
            "db_url_type": eng.url.get_backend_name(),
        },
        "summary": {
            "total_rules": total,
            "passed": len(passed),
            "warn": len(warned),
            "failed": len(failed),
            "score": score,
            "coverage_rate": coverage,
            "covered_fields": covered,
            "key_fields": key_total,
            "blocking": any(r["level"] == "BLOCK" and r["status"] == FAIL for r in results),
        },
        "alerts": alerts,
        "results": results,
    }

    # 站内信告警推送（含送达耗时与及时率），满足「异常数据告警通知」要求
    notify_summary: dict[str, Any] = {"channel": "", "total": 0, "delivered": 0, "timely": 0, "timeliness_rate": 100.0}
    if notify:
        from etl.jobs.alert_notify import publish_alerts

        notify_summary = publish_alerts(alerts, bd, engine=eng)
    report["summary"]["notify"] = notify_summary
    report["summary"]["alert_total"] = notify_summary.get("total", 0)

    out_dir = LOG_DIR if output_dir is None else __import__("pathlib").Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_file = out_dir / f"quality_report_{bd:%Y%m%d}.json"
    with report_file.open("w", encoding="utf-8") as fp:
        json.dump(report, fp, ensure_ascii=False, indent=2)

    print(f"\n[质量] 批次 {bd} 报告：{report_file}")
    print(f"[质量] 规则 {total} 条：通过 {len(passed)} / 告警 {len(warned)} / 失败 {len(failed)}，评分 {score}，字段覆盖率 {coverage}%（{covered}/{key_total}）")
    if alerts:
        print("[质量] 告警清单：")
        for a in alerts:
            print(f"  [{a['level']:<5}][{a['rule_code']}] {a['table']:<28} {a['detail']}")
    else:
        print("[质量] 无告警")
    if report["summary"]["blocking"]:
        print("[质量] 存在阻断级规则失败，下游发布应中止并通知数据责任人")
    if raise_on_block and report["summary"]["blocking"]:
        raise QualityBlockedError(bd, [a for a in alerts if a["level"] == "BLOCK" and a["status"] != PASS])
    return report


if __name__ == "__main__":  # 手工自检：python -m etl.jobs.quality_check
    from etl.config.settings import DEFAULT_BATCH_DATE

    generate_quality_report(DEFAULT_BATCH_DATE)
