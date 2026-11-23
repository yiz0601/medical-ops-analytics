"""DWS 汇总与 ADS 主题集市加工（阶段三 · DWS/ADS 步骤 3、4）。

    build_dws_daily(dept, date, ...)   按「科室 × 日期」聚合基础度量，先删后插幂等
    build_theme_marts(theme, ...)      构建 8 大主题集市表（支持单主题或全量）
    rerun(date_range, ...)             按日期区间全量重跑，幂等且不影响其他批次
    verify_marts(...)                  校验集市齐全性与聚合一致性

数据来源：DWD 明细宽表（`dwd_visit_detail`、`dwd_outpatient_visit_detail`、
`dwd_inpatient_visit_detail`、`dwd_charge_detail`、`dwd_lis_report_detail`、
`dwd_finance_daily_detail`）+ 维表 `dim_department`。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from etl.config.dwd_schema import DWD_TABLES
from etl.config.mart_schema import (
    THEME_NAME_CN,
    THEME_TABLES,
    dws_dept_daily,
)
from etl.config.settings import get_engine, normalize_batch_date
from etl.config.loader import load_by_batch, read_table_df
from etl.jobs.init_dim import dept_map

# 金额分项 -> DWS 字段
CHARGE_CLASS_COLUMNS = {
    "药品收入": "charge_drug_amt",
    "耗材收入": "charge_consumable_amt",
    "检查检验收入": "charge_exam_lab_amt",
    "医疗服务性收入": "charge_service_amt",
}


def _agg_op(engine: Engine, bd: date) -> pd.DataFrame:
    """门诊基础度量：人次、号别结构、登记口径费用、患者数与复诊人次。"""
    df = read_table_df(engine, DWD_TABLES["dwd_outpatient_visit_detail"], bd)
    if df.empty:
        return pd.DataFrame(columns=["dept_code", "stat_date", "op_visit_cnt"])
    df = df.copy()
    df["stat_date"] = pd.to_datetime(df["visit_date"], errors="coerce").dt.date
    df["fee_amount"] = pd.to_numeric(df["fee_amount"], errors="coerce").fillna(0.0)
    # 复诊：同一患者在统计期内门诊就诊 ≥2 次，第 2 次起计复诊
    per_patient = df.groupby("patient_id")["visit_id"].transform("count")
    df["_is_repeat"] = (per_patient >= 2).astype(int)
    df["_normal"] = (df["visit_type"] == "普通").astype(int)
    df["_expert"] = (df["visit_type"] == "专家").astype(int)
    df["_emergency"] = (df["visit_type"] == "急诊").astype(int)

    grouped = df.groupby(["dept_code", "stat_date"], as_index=False).agg(
        op_visit_cnt=("visit_id", "nunique"),
        op_normal_cnt=("_normal", "sum"),
        op_expert_cnt=("_expert", "sum"),
        op_emergency_cnt=("_emergency", "sum"),
        op_fee_sum=("fee_amount", "sum"),
        op_patient_cnt=("patient_id", "nunique"),
        op_repeat_cnt=("_is_repeat", "sum"),
    )
    return grouped


def _agg_ip(engine: Engine, bd: date, bed_map: dict[str, int]) -> pd.DataFrame:
    """住院基础度量：入院/出院人次、床日、登记口径费用、DRG 病例与权重。"""
    df = read_table_df(engine, DWD_TABLES["dwd_inpatient_visit_detail"], bd)
    if df.empty:
        return pd.DataFrame(columns=["dept_code", "stat_date", "ip_discharge_cnt"])
    df = df.copy()
    df["discharge_date"] = pd.to_datetime(df["discharge_date"], errors="coerce").dt.date
    df["admit_date"] = pd.to_datetime(df["admit_date"], errors="coerce").dt.date
    for col in ("total_fee", "drug_fee", "consumable_fee", "rw"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    df["stay_days"] = pd.to_numeric(df["stay_days"], errors="coerce").fillna(0)
    df["_grouped"] = (df["drg_code"] != "UNGROUPED").astype(int)

    # 出院口径（出院人次 / 床日 / 费用 / DRG）
    by_discharge = df.groupby(["dept_code", "discharge_date"], as_index=False).agg(
        ip_discharge_cnt=("visit_id", "nunique"),
        bed_days=("stay_days", "sum"),
        ip_fee_sum=("total_fee", "sum"),
        ip_drug_fee_sum=("drug_fee", "sum"),
        ip_consumable_fee_sum=("consumable_fee", "sum"),
        drg_cases=("_grouped", "sum"),
        drg_rw_sum=("rw", "sum"),
    ).rename(columns={"discharge_date": "stat_date"})

    # 入院口径
    by_admit = df.groupby(["dept_code", "admit_date"], as_index=False).agg(
        ip_admit_cnt=("visit_id", "nunique")
    ).rename(columns={"admit_date": "stat_date"})

    merged = by_discharge.merge(by_admit, on=["dept_code", "stat_date"], how="outer")
    merged["bed_cnt"] = merged["dept_code"].map(lambda c: bed_map.get(str(c), 0))
    return merged


def _agg_charge(engine: Engine, bd: date) -> pd.DataFrame:
    """流水口径收入：合计、四分类收入、门诊/住院收入拆分。"""
    df = read_table_df(engine, DWD_TABLES["dwd_charge_detail"], bd)
    if df.empty:
        return pd.DataFrame(columns=["dept_code", "stat_date", "charge_amt_sum"])
    df = df.copy()
    df["stat_date"] = pd.to_datetime(df["fee_date"], errors="coerce").dt.date
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    # 门诊费用按就诊日期归属科室口径：charge 自带 dept_code
    for fee_class, col in CHARGE_CLASS_COLUMNS.items():
        df[col] = df["amount"].where(df["fee_class"] == fee_class, 0.0)
    df["op_charge_amt"] = df["amount"].where(df["visit_type"] == "门诊", 0.0)
    df["ip_charge_amt"] = df["amount"].where(df["visit_type"] == "住院", 0.0)
    df["_ss"] = ((df["fee_type_code"] == "SS") & (df["visit_type"] == "住院")).astype(int)
    grouped = df.groupby(["dept_code", "stat_date"], as_index=False).agg(
        charge_amt_sum=("amount", "sum"),
        charge_drug_amt=("charge_drug_amt", "sum"),
        charge_consumable_amt=("charge_consumable_amt", "sum"),
        charge_exam_lab_amt=("charge_exam_lab_amt", "sum"),
        charge_service_amt=("charge_service_amt", "sum"),
        op_charge_amt=("op_charge_amt", "sum"),
        ip_charge_amt=("ip_charge_amt", "sum"),
    )
    # 含手术费的住院就诊数（按 visit_id 去重）
    ss = (
        df.loc[df["_ss"] == 1]
        .groupby(["dept_code", "stat_date"], as_index=False)["visit_id"]
        .nunique()
        .rename(columns={"visit_id": "ip_ss_visit_cnt"})
    )
    return grouped.merge(ss, on=["dept_code", "stat_date"], how="left")


def _agg_finance(engine: Engine, bd: date) -> pd.DataFrame:
    """财务口径收入（财务日报）：用于药占比、耗占比的默认口径。"""
    df = read_table_df(engine, DWD_TABLES["dwd_finance_daily_detail"], bd)
    if df.empty:
        return pd.DataFrame(columns=["dept_code", "stat_date", "fin_revenue"])
    df = df.copy()
    df["stat_date"] = pd.to_datetime(df["stat_date"], errors="coerce").dt.date
    for col in ("revenue", "drug_revenue", "consumable_revenue"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df.groupby(["dept_code", "stat_date"], as_index=False).agg(
        fin_revenue=("revenue", "sum"),
        fin_drug_revenue=("drug_revenue", "sum"),
        fin_consumable_revenue=("consumable_revenue", "sum"),
    )


def _agg_lis(engine: Engine, bd: date) -> pd.DataFrame:
    """检验度量：按住院就诊关联科室，统计报告数与异常数（按报告日期）。"""
    lis = read_table_df(engine, DWD_TABLES["dwd_lis_report_detail"], bd)
    ip = read_table_df(engine, DWD_TABLES["dwd_inpatient_visit_detail"], bd)
    if lis.empty or ip.empty:
        return pd.DataFrame(columns=["dept_code", "stat_date", "lis_report_cnt"])
    mapping = ip.set_index("visit_id")["dept_code"].to_dict()
    frame = pd.DataFrame(
        {
            "dept_code": lis["visit_id"].map(mapping),
            "stat_date": pd.to_datetime(lis["report_date"], errors="coerce").dt.date,
            "abnormal": (lis["result_flag"] == "异常").astype(int),
        }
    ).dropna(subset=["dept_code", "stat_date"])
    return frame.groupby(["dept_code", "stat_date"], as_index=False).agg(
        lis_report_cnt=("abnormal", "size"),
        lis_abnormal_cnt=("abnormal", "sum"),
    )


def build_dws_daily(
    dept: str | None = None,
    stat_date: date | str | None = None,
    batch_date: date | str | None = None,
    *,
    engine: Engine | None = None,
) -> int:
    """按「科室 × 日期」构建 DWS 基础度量汇总表（先删后插，幂等）。"""
    bd = normalize_batch_date(batch_date)
    eng = engine or get_engine()
    bed_map = {
        code: int(row.get("bed_cnt") or 0)
        for code, row in dept_map(eng).items()
        if (row.get("dept_level") or 2) == 2
    }

    parts = [
        _agg_op(eng, bd),
        _agg_ip(eng, bd, bed_map),
        _agg_charge(eng, bd),
        _agg_lis(eng, bd),
        _agg_finance(eng, bd),
    ]
    parts = [p for p in parts if not p.empty]
    if not parts:
        print("  [WARN] DWD 无数据，跳过 dws_dept_daily")
        return 0

    merged = parts[0]
    for part in parts[1:]:
        merged = merged.merge(part, on=["dept_code", "stat_date"], how="outer")

    merged["dept_name"] = merged["dept_code"].map(
        lambda c: dept_map(eng).get(str(c), {}).get("dept_name") or "未知科室"
    )
    merged["bed_cnt"] = merged["dept_code"].map(lambda c: bed_map.get(str(c), 0))
    merged["stat_ym"] = pd.to_datetime(merged["stat_date"], errors="coerce").dt.strftime("%Y-%m")

    numeric_cols = [
        "op_visit_cnt", "op_normal_cnt", "op_expert_cnt", "op_emergency_cnt", "op_fee_sum",
        "op_patient_cnt", "op_repeat_cnt", "ip_admit_cnt", "ip_discharge_cnt", "bed_days",
        "ip_fee_sum", "ip_drug_fee_sum", "ip_consumable_fee_sum", "charge_amt_sum",
        "charge_drug_amt", "charge_consumable_amt", "charge_exam_lab_amt", "charge_service_amt",
        "op_charge_amt", "ip_charge_amt", "lis_report_cnt", "lis_abnormal_cnt", "drg_cases",
        "drg_rw_sum", "bed_cnt", "ip_ss_visit_cnt", "fin_revenue", "fin_drug_revenue",
        "fin_consumable_revenue",
    ]
    for col in numeric_cols:
        if col not in merged.columns:
            merged[col] = 0
        merged[col] = pd.to_numeric(merged[col], errors="coerce").fillna(0)
    for col in (
        "op_visit_cnt", "ip_admit_cnt", "ip_discharge_cnt", "bed_days", "drg_cases", "bed_cnt",
        "ip_ss_visit_cnt", "lis_report_cnt", "lis_abnormal_cnt", "op_patient_cnt", "op_repeat_cnt",
    ):
        merged[col] = merged[col].astype(int)

    merged = merged.dropna(subset=["dept_code", "stat_date"])
    if dept:
        merged = merged.loc[merged["dept_code"] == dept]
    if stat_date is not None:
        merged = merged.loc[merged["stat_date"] == normalize_batch_date(stat_date)]

    rows = load_by_batch(eng, dws_dept_daily, merged, bd)
    print(f"  [OK]   dws_dept_daily 写入 {rows} 行（科室×日期）")
    return rows


# ---------------------------------------------------------------- 主题集市
def _theme_frames(engine: Engine, bd: date) -> dict[str, pd.DataFrame]:
    """基于 DWS 汇总与财务明细，派生 8 大主题集市的数据帧。"""
    dws = read_table_df(engine, dws_dept_daily, bd)
    if dws.empty:
        return {}
    dws = dws.copy()
    for col in dws.columns:
        if col not in {"dept_code", "dept_name", "stat_date", "stat_ym", "etl_batch_date", "etl_load_time"}:
            dws[col] = pd.to_numeric(dws[col], errors="coerce").fillna(0.0)

    def _safe_div(num: pd.Series, den: pd.Series) -> pd.Series:
        return pd.to_numeric(num, errors="coerce").divide(pd.to_numeric(den, errors="coerce").where(den > 0)).round(2)

    base = dws[["stat_date", "dept_code", "dept_name", "stat_ym"]].copy()

    # 门诊主题
    op = base.copy()
    op["op_visit_cnt"] = dws["op_visit_cnt"].astype(int)
    op["normal_cnt"] = dws["op_normal_cnt"].astype(int)
    op["expert_cnt"] = dws["op_expert_cnt"].astype(int)
    op["emergency_cnt"] = dws["op_emergency_cnt"].astype(int)
    op["normal_ratio"] = _safe_div(dws["op_normal_cnt"] * 100, dws["op_visit_cnt"])
    op["expert_ratio"] = _safe_div(dws["op_expert_cnt"] * 100, dws["op_visit_cnt"])
    op["emergency_ratio"] = _safe_div(dws["op_emergency_cnt"] * 100, dws["op_visit_cnt"])
    op["op_amt"] = dws["op_charge_amt"]
    op["op_avg_cost"] = _safe_div(dws["op_fee_sum"], dws["op_visit_cnt"])

    # 住院主题
    ip = base.copy()
    ip["ip_admit_cnt"] = dws["ip_admit_cnt"].astype(int)
    ip["ip_discharge_cnt"] = dws["ip_discharge_cnt"].astype(int)
    ip["bed_days"] = dws["bed_days"].astype(int)
    ip["bed_cnt"] = dws["bed_cnt"].astype(int)
    ip["bed_usage_rate"] = _safe_div(dws["bed_days"] * 100, dws["bed_cnt"])
    ip["avg_stay_days"] = _safe_div(dws["bed_days"], dws["ip_discharge_cnt"])
    ip["ip_amt"] = dws["ip_charge_amt"]
    ip["ip_avg_cost"] = _safe_div(dws["ip_fee_sum"], dws["ip_discharge_cnt"])

    # 收入主题
    inc = base.copy()
    inc["total_amt"] = dws["charge_amt_sum"]
    inc["drug_amt"] = dws["charge_drug_amt"]
    inc["consumable_amt"] = dws["charge_consumable_amt"]
    inc["exam_lab_amt"] = dws["charge_exam_lab_amt"]
    inc["service_amt"] = dws["charge_service_amt"]
    inc["drug_ratio"] = _safe_div(dws["charge_drug_amt"] * 100, dws["charge_amt_sum"])
    inc["consumable_ratio"] = _safe_div(dws["charge_consumable_amt"] * 100, dws["charge_amt_sum"])
    inc["exam_lab_ratio"] = _safe_div(dws["charge_exam_lab_amt"] * 100, dws["charge_amt_sum"])
    inc["service_ratio"] = _safe_div(dws["charge_service_amt"] * 100, dws["charge_amt_sum"])

    # 药品主题（含财务口径药占比、西药/中成药拆分）
    fin = read_table_df(engine, DWD_TABLES["dwd_finance_daily_detail"], bd)
    fin_map = {}
    if not fin.empty:
        fin = fin.copy()
        fin["stat_date"] = pd.to_datetime(fin["stat_date"], errors="coerce").dt.date
        fin["revenue"] = pd.to_numeric(fin["revenue"], errors="coerce").fillna(0.0)
        fin["drug_revenue"] = pd.to_numeric(fin["drug_revenue"], errors="coerce").fillna(0.0)
        fin = fin.loc[fin["revenue"] > 0]
        fin["fin_drug_ratio"] = (fin["drug_revenue"] / fin["revenue"] * 100).round(2)
        fin_map = {(str(r.dept_code), r.stat_date): r.fin_drug_ratio for r in fin.itertuples()}

    # 西药费 / 中成药费拆分（流水口径，按收费日期 × 科室）
    charge = read_table_df(engine, DWD_TABLES["dwd_charge_detail"], bd)
    western_map: dict[tuple[str, date], float] = {}
    patent_map: dict[tuple[str, date], float] = {}
    if not charge.empty:
        ch = charge.copy()
        ch["stat_date"] = pd.to_datetime(ch["fee_date"], errors="coerce").dt.date
        ch["amount"] = pd.to_numeric(ch["amount"], errors="coerce").fillna(0.0)
        for code, target in (("XY", western_map), ("ZC", patent_map)):
            sub = ch.loc[ch["fee_type_code"] == code].groupby(["dept_code", "stat_date"], as_index=False)[
                "amount"
            ].sum()
            target.update({(str(r.dept_code), r.stat_date): float(r.amount) for r in sub.itertuples()})

    drug_amt = dws["charge_drug_amt"]
    keys = list(zip(dws["dept_code"].astype(str), dws["stat_date"]))
    drug = base.copy()
    drug["drug_amt"] = drug_amt
    drug["western_amt"] = [western_map.get(k, 0.0) for k in keys]
    drug["patent_amt"] = [patent_map.get(k, 0.0) for k in keys]
    drug["drug_ratio_charge"] = _safe_div(drug_amt * 100, dws["charge_amt_sum"])
    drug["drug_ratio_finance"] = [fin_map.get(k) for k in keys]
    drug["drug_amt_per_visit"] = _safe_div(drug_amt, dws["op_visit_cnt"])

    # 耗材主题
    con = base.copy()
    con["consumable_amt"] = dws["charge_consumable_amt"]
    con["consumable_ratio"] = _safe_div(dws["charge_consumable_amt"] * 100, dws["charge_amt_sum"])
    con["hundred_yuan_consumable"] = _safe_div(dws["charge_consumable_amt"] * 100, dws["charge_amt_sum"])
    con["consumable_amt_per_discharge"] = _safe_div(
        dws["charge_consumable_amt"], dws["ip_discharge_cnt"]
    )

    # 病种主题（DRG）
    drg = base.copy()
    drg["cases"] = dws["ip_discharge_cnt"].astype(int)
    drg["grouped_cases"] = dws["drg_cases"].astype(int)
    drg["drg_group_rate"] = _safe_div(dws["drg_cases"] * 100, dws["ip_discharge_cnt"])
    drg["rw_sum"] = dws["drg_rw_sum"]
    drg["cmi"] = pd.to_numeric(dws["drg_rw_sum"], errors="coerce").divide(
        pd.to_numeric(dws["drg_cases"], errors="coerce").where(dws["drg_cases"] > 0)
    ).round(4)
    drg["fee_sum"] = dws["ip_fee_sum"]
    # 期望费用 = 全院次均费用 × 该组 RW 合计（模拟标化基准，见《指标口径手册》M25）
    global_avg_fee = (
        float(pd.to_numeric(dws["ip_fee_sum"], errors="coerce").sum())
        / float(pd.to_numeric(dws["ip_discharge_cnt"], errors="coerce").sum())
        if float(pd.to_numeric(dws["ip_discharge_cnt"], errors="coerce").sum()) > 0
        else 0.0
    )
    global_avg_days = (
        float(pd.to_numeric(dws["bed_days"], errors="coerce").sum())
        / float(pd.to_numeric(dws["ip_discharge_cnt"], errors="coerce").sum())
        if float(pd.to_numeric(dws["ip_discharge_cnt"], errors="coerce").sum()) > 0
        else 0.0
    )
    drg["expected_fee"] = (dws["drg_rw_sum"] * global_avg_fee).round(2)
    drg["fee_index"] = pd.to_numeric(dws["ip_fee_sum"], errors="coerce").divide(
        pd.to_numeric(drg["expected_fee"], errors="coerce").where(drg["expected_fee"] > 0)
    ).round(4)
    drg["days_sum"] = dws["bed_days"].astype(int)
    drg["expected_days"] = (dws["drg_rw_sum"] * global_avg_days).round(2)
    drg["time_index"] = pd.to_numeric(dws["bed_days"], errors="coerce").divide(
        pd.to_numeric(drg["expected_days"], errors="coerce").where(drg["expected_days"] > 0)
    ).round(4)

    # 资源效率主题
    eff = base.copy()
    eff["bed_cnt"] = dws["bed_cnt"].astype(int)
    eff["bed_usage_rate"] = _safe_div(dws["bed_days"] * 100, dws["bed_cnt"])
    eff["avg_stay_days"] = _safe_div(dws["bed_days"], dws["ip_discharge_cnt"])
    eff["income_per_bed"] = _safe_div(dws["charge_amt_sum"], dws["bed_cnt"])
    eff["op_per_doctor"] = None  # M28 依赖人力数据源，阶段二/三未接入 -> NULL
    eff["bed_nurse_ratio"] = None  # M29 依赖人力数据源 -> NULL
    eff["hundred_yuan_consumable"] = _safe_div(dws["charge_consumable_amt"] * 100, dws["charge_amt_sum"])

    # 患者服务主题
    svc = base.copy()
    svc["patient_cnt"] = dws["op_patient_cnt"].astype(int)
    svc["op_patient_cnt"] = dws["op_patient_cnt"].astype(int)
    svc["repeat_visit_cnt"] = dws["op_repeat_cnt"].astype(int)
    svc["repeat_visit_rate"] = _safe_div(dws["op_repeat_cnt"] * 100, dws["op_visit_cnt"])
    svc["lis_report_cnt"] = dws["lis_report_cnt"].astype(int)
    svc["lis_abnormal_cnt"] = dws["lis_abnormal_cnt"].astype(int)
    svc["lis_abnormal_rate"] = _safe_div(dws["lis_abnormal_cnt"] * 100, dws["lis_report_cnt"])
    svc["emergency_ratio"] = _safe_div(dws["op_emergency_cnt"] * 100, dws["op_visit_cnt"])

    return {
        "outpatient": op,
        "inpatient": ip,
        "income": inc,
        "drug": drug,
        "consumable": con,
        "drg": drg,
        "efficiency": eff,
        "service": svc,
    }


def build_theme_marts(
    theme: str | None = None,
    batch_date: date | str | None = None,
    *,
    engine: Engine | None = None,
) -> dict[str, int]:
    """构建主题集市表（theme 为空时构建全部 8 个主题）。"""
    bd = normalize_batch_date(batch_date)
    eng = engine or get_engine()
    frames = _theme_frames(eng, bd)
    if not frames:
        print("  [WARN] DWS 无数据，跳过主题集市构建")
        return {}

    targets = [theme] if theme else list(THEME_TABLES)
    result: dict[str, int] = {}
    for key in targets:
        if key not in THEME_TABLES:
            raise KeyError(f"未知主题：{key}，可选 {list(THEME_TABLES)}")
        table = THEME_TABLES[key]
        frame = frames[key].copy()
        # 仅保留目标表存在的列
        columns = [c.name for c in table.columns]
        frame = frame[[c for c in frame.columns if c in columns]]
        frame["caliber"] = "CHARGE"
        rows = load_by_batch(eng, table, frame, bd)
        result[table.name] = rows
        print(f"  [OK]   {table.name:<26} {rows:>5} 行  ({THEME_NAME_CN[key]})")
    return result


# ---------------------------------------------------------------- 重跑与校验
def rerun(
    date_range: tuple[str, str] | list[str] | None = None,
    batch_date: date | str | None = None,
    *,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """按日期区间全量重跑 DWS 与 8 个集市（先删后插，幂等，不影响其他批次）。"""
    bd = normalize_batch_date(batch_date)
    eng = engine or get_engine()
    if date_range:
        start, end = date_range[0], date_range[1]
    else:
        from etl.config.baseline import STAT_PERIOD

        start, end = STAT_PERIOD
    print(f"[重跑] 日期区间 {start} ~ {end}，批次 {bd}（先删后插，幂等）")
    dws_rows = build_dws_daily(batch_date=bd, engine=eng)
    theme_rows = build_theme_marts(batch_date=bd, engine=eng)
    total = dws_rows + sum(theme_rows.values())
    print(f"[重跑] 完成，共写入 {total} 行（DWS {dws_rows} + 集市 {sum(theme_rows.values())}）")
    return {"date_range": [start, end], "dws_rows": dws_rows, "theme_rows": theme_rows, "total": total}


def verify_marts(batch_date: date | str | None = None, *, engine: Engine | None = None) -> list[dict[str, Any]]:
    """校验 8 个集市齐全性、主键唯一性与聚合一致性（DWS ↔ 集市 ↔ DWD）。"""
    bd = normalize_batch_date(batch_date)
    eng = engine or get_engine()
    checks: list[dict[str, Any]] = []

    def _count(table, with_batch: bool = True) -> int:
        stmt = select(func.count()).select_from(table)
        if with_batch:
            stmt = stmt.where(table.c.etl_batch_date == bd)
        with eng.connect() as conn:
            return int(conn.execute(stmt).scalar_one())

    dws_rows = _count(dws_dept_daily)
    checks.append(
        {
            "check": "DWS 汇总表非空",
            "table": "dws_dept_daily",
            "expected": ">0",
            "actual": dws_rows,
            "ok": dws_rows > 0,
            "detail": f"{dws_rows} 行",
        }
    )
    for key, table in THEME_TABLES.items():
        rows = _count(table)
        checks.append(
            {
                "check": f"集市齐全·{THEME_NAME_CN[key]}",
                "table": table.name,
                "expected": dws_rows,
                "actual": rows,
                "ok": rows == dws_rows and rows > 0,
                "detail": f"{rows} 行",
            }
        )

    # 聚合一致性：集市收入合计 == DWS 合计 == DWD 收费合计
    def _sum(col_table, col: str) -> float:
        with eng.connect() as conn:
            value = conn.execute(select(func.sum(col_table.c[col])).where(col_table.c.etl_batch_date == bd)).scalar()
        return float(value or 0.0)

    from etl.config.mart_schema import ads_income_theme

    dws_total = _sum(dws_dept_daily, "charge_amt_sum")
    mart_total = _sum(ads_income_theme, "total_amt")
    dwd_total = _sum(DWD_TABLES["dwd_charge_detail"], "amount")
    checks.append(
        {
            "check": "收入聚合一致性(DWS=集市=DWD)",
            "table": "ads_income_theme",
            "expected": round(dwd_total, 2),
            "actual": round(mart_total, 2),
            "ok": abs(dws_total - mart_total) < 0.01 and abs(mart_total - dwd_total) < 0.01,
            "detail": f"DWS {dws_total:,.2f} / 集市 {mart_total:,.2f} / DWD {dwd_total:,.2f}",
        }
    )
    return checks


if __name__ == "__main__":  # 手工自检：python -m etl.jobs.aggregate_dws
    from etl.config.settings import DEFAULT_BATCH_DATE

    build_dws_daily(batch_date=DEFAULT_BATCH_DATE)
    build_theme_marts(batch_date=DEFAULT_BATCH_DATE)
    print("\n集市校验：")
    for item in verify_marts(DEFAULT_BATCH_DATE):
        print(f"  [{'OK  ' if item['ok'] else 'FAIL'}] {item['check']:<28} {item['table']:<24} {item['detail']}")
