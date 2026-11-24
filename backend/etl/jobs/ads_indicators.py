"""指标计算函数族、批量计算与回刷、手工 SQL 对账（阶段三 · 指标步骤 2、3、4）。

设计要点
    * 统一签名：`calc_xxx(start_date, end_date, granularity="month", *, engine=None, dept=None)`
      返回 DataFrame，列固定为
      `metric_code, metric_name, theme, dim_value, granularity, stat_date, metric_value, unit, data_status`
    * 数据来源：DWS 汇总表 `dws_dept_daily`（科室×日）+ 维表；不直接扫 ODS
    * 维度值：科室编码或 `ALL`（全院）；M02 的维度值格式为 `<科室>@<号别>`
    * 数据源缺失的指标（M04/M05/M27）返回 `metric_value=NULL`、`data_status=PENDING`
    * 结果落 `ads_indicator_result`，唯一键 = 指标编码 + 维度值 + 粒度 + 统计日期
"""

from __future__ import annotations

import json
import time
from datetime import date, datetime
from typing import Any, Callable, Sequence

import pandas as pd
from sqlalchemy import delete, func, select, text
from sqlalchemy.engine import Engine

from etl.config.baseline import STAT_DAYS, TOTAL_BEDS
from etl.config.loader import read_table_df
from etl.config.mart_schema import ads_indicator_result, dws_dept_daily
from etl.config.settings import LOG_DIR, batch_id_of, get_engine, normalize_batch_date
from etl.jobs.init_dim import dept_map

INDICATOR_LOG = LOG_DIR / "indicator_run.log"

# 指标注册表：metric_code -> {name, theme, unit, func, data_status}
REGISTRY: dict[str, dict[str, Any]] = {}

NON_MEASURE_COLUMNS = {
    "stat_date",
    "dept_code",
    "dept_name",
    "stat_ym",
    "etl_batch_date",
    "etl_load_time",
    "period_date",
    "granularity",
    "dim_value",
}


def register(metric_code: str, metric_name: str, theme: str, unit: str) -> Callable:
    """注册指标函数（供 `run_indicators` 批量调用）。"""

    def decorator(func: Callable) -> Callable:
        REGISTRY[metric_code] = {
            "code": metric_code,
            "name": metric_name,
            "theme": theme,
            "unit": unit,
            "func": func,
        }
        return func

    return decorator


# ---------------------------------------------------------------- 公共准备
def _period_end(dates: pd.Series, granularity: str, end_date: date) -> pd.Series:
    """把统计日期映射到粒度对应的统计期末日期。"""
    series = pd.to_datetime(pd.Series(list(dates)), errors="coerce")
    if granularity == "day":
        return series.dt.date
    if granularity == "month":
        return (series + pd.offsets.MonthEnd(0)).dt.date
    return pd.Series([end_date] * len(series))


def _staff_map(engine: Engine, end_date: date | str | None = None) -> dict[str, dict[str, Any]]:
    """科室人力映射：优先取人事系统人力台账（DWD 接入），缺失时回退科室维表维护值。

    人力数据源（sources.json 中的 `hr_staff`，系统类型 HR）经 ODS/DWD 落地后在此取数，
    支撑 M28 医师人均门诊人次与 M29 床护比；台账按 stat_date 取期末快照（≤ 统计期末）。
    """
    try:
        from etl.config.dwd_schema import dwd_hr_staff_detail

        frame = read_table_df(engine, dwd_hr_staff_detail)
    except Exception:  # noqa: BLE001 - 表未创建或读取失败时回退维表
        frame = pd.DataFrame()
    if frame is not None and not frame.empty:
        frame = frame.copy()
        frame["stat_date"] = pd.to_datetime(frame["stat_date"], errors="coerce").dt.date
        if end_date is not None:
            frame = frame.loc[frame["stat_date"] <= normalize_batch_date(end_date)]
        if not frame.empty:
            latest = frame.sort_values("stat_date").groupby("dept_code", as_index=False).last()
            return {
                str(row["dept_code"]): {
                    "doctor_cnt": int(row.get("doctor_cnt") or 0),
                    "nurse_cnt": int(row.get("nurse_cnt") or 0),
                    "dept_level": int(row.get("dept_level") or 2),
                }
                for row in latest.to_dict("records")
            }
    staff = dept_map(engine)
    return {
        str(code): {
            "doctor_cnt": int(row.get("doctor_cnt") or 0),
            "nurse_cnt": int(row.get("nurse_cnt") or 0),
            "dept_level": int(row.get("dept_level") or 2),
        }
        for code, row in staff.items()
    }


def _prepared(
    start_date: str,
    end_date: str,
    granularity: str = "month",
    *,
    engine: Engine | None = None,
    dept: str | None = None,
) -> pd.DataFrame:
    """读取 DWS 并按（维度值 × 粒度）聚合，附带全院 ALL 行与人力维表快照。"""
    eng = engine or get_engine()
    dws = read_table_df(eng, dws_dept_daily)
    if dws.empty:
        return pd.DataFrame()
    dws = dws.copy()
    dws["stat_date"] = pd.to_datetime(dws["stat_date"], errors="coerce").dt.date
    start = normalize_batch_date(start_date)
    end = normalize_batch_date(end_date)
    dws = dws.loc[(dws["stat_date"] >= start) & (dws["stat_date"] <= end)]
    if dept:
        dws = dws.loc[dws["dept_code"] == dept]
    if dws.empty:
        return pd.DataFrame()

    dws["period_date"] = _period_end(dws["stat_date"], granularity, end)
    dws["granularity"] = granularity
    measures = [c for c in dws.columns if c not in NON_MEASURE_COLUMNS]

    dept_grp = dws.groupby(["dept_code", "period_date", "granularity"], as_index=False)[measures].sum()
    dept_grp = dept_grp.rename(columns={"dept_code": "dim_value"})
    # 统计天数（每维度每粒度），用于把日快照度量（床位/人力）还原为日均值
    day_counts = dws.groupby(["dept_code", "period_date", "granularity"], as_index=False)["stat_date"].nunique()
    day_counts = day_counts.rename(columns={"dept_code": "dim_value", "stat_date": "stat_days"})
    dept_grp = dept_grp.merge(day_counts, on=["dim_value", "period_date", "granularity"], how="left")

    staff = _staff_map(eng, end)
    dept_grp["staff_doctor"] = dept_grp["dim_value"].map(lambda c: int(staff.get(str(c), {}).get("doctor_cnt") or 0))
    dept_grp["staff_nurse"] = dept_grp["dim_value"].map(lambda c: int(staff.get(str(c), {}).get("nurse_cnt") or 0))

    all_grp = dws.groupby(["period_date", "granularity"], as_index=False)[measures].sum()
    all_grp["dim_value"] = "ALL"
    all_days = dws.groupby(["period_date", "granularity"], as_index=False)["stat_date"].nunique()
    all_days = all_days.rename(columns={"stat_date": "stat_days"})
    all_grp = all_grp.merge(all_days, on=["period_date", "granularity"], how="left")
    all_grp["staff_doctor"] = sum(
        int(row.get("doctor_cnt") or 0) for row in staff.values() if int(row.get("dept_level") or 2) == 2
    )
    all_grp["staff_nurse"] = sum(
        int(row.get("nurse_cnt") or 0) for row in staff.values() if int(row.get("dept_level") or 2) == 2
    )

    frame = pd.concat([dept_grp, all_grp], ignore_index=True)
    # 统一转为 float：MySQL/SQLite 的 DECIMAL 会以 Decimal 返回，直接参与算术会抛 TypeError
    for col in measures:
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce").astype("float64")
    for col in ("staff_doctor", "staff_nurse", "stat_days"):
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce").astype("float64")
    return frame.sort_values(["dim_value", "period_date"]).reset_index(drop=True)


def _emit(
    metric_code: str,
    frame: pd.DataFrame,
    values: Sequence[Any] | pd.Series | None,
    *,
    status: str = "OK",
    dim_values: Sequence[str] | None = None,
) -> pd.DataFrame:
    """把计算结果组装成标准指标结果 DataFrame。"""
    meta = REGISTRY[metric_code]
    if values is None:
        metric_values = pd.Series([None] * len(frame), dtype="float64")
    else:
        metric_values = pd.to_numeric(pd.Series(list(values)), errors="coerce").round(4).reset_index(drop=True)
    return pd.DataFrame(
        {
            "metric_code": metric_code,
            "metric_name": meta["name"],
            "theme": meta["theme"],
            "dim_value": list(dim_values) if dim_values is not None else frame["dim_value"].astype(str).tolist(),
            "granularity": frame["granularity"].tolist(),
            "stat_date": frame["period_date"].tolist(),
            "metric_value": metric_values.tolist(),
            "unit": meta["unit"],
            "data_status": status,
        }
    )


def _pending(metric_code: str, frame: pd.DataFrame) -> pd.DataFrame:
    """数据源缺失的指标：值记 NULL，状态 PENDING。"""
    return _emit(metric_code, frame, None, status="PENDING")


def _ratio(num: pd.Series, den: pd.Series, scale: float = 1.0) -> pd.Series:
    """安全比率（分母为 0 时返回 NaN）。"""
    n = pd.to_numeric(num, errors="coerce")
    d = pd.to_numeric(den, errors="coerce")
    return (n * scale).divide(d.where(d > 0))


# ---------------------------------------------------------------- 门诊主题
@register("M01", "门诊人次", "门诊", "人次")
def calc_outpatient_volume(start_date, end_date, granularity="month", *, engine=None, dept=None) -> pd.DataFrame:
    """门诊人次 = COUNT(DISTINCT visit_id)，按科室 × 粒度。"""
    frame = _prepared(start_date, end_date, granularity, engine=engine, dept=dept)
    if frame.empty:
        return frame
    return _emit("M01", frame, frame["op_visit_cnt"])


@register("M02", "门诊号别结构占比", "门诊", "%")
def calc_visit_type_structure(start_date, end_date, granularity="month", *, engine=None, dept=None) -> pd.DataFrame:
    """号别结构占比：普通/专家/急诊，维度值格式 `<科室>@<号别>`。"""
    frame = _prepared(start_date, end_date, granularity, engine=engine, dept=dept)
    if frame.empty:
        return frame
    parts = []
    for label, col in (("普通", "op_normal_cnt"), ("专家", "op_expert_cnt"), ("急诊", "op_emergency_cnt")):
        parts.append(
            _emit(
                "M02",
                frame,
                _ratio(frame[col], frame["op_visit_cnt"], 100),
                dim_values=[f"{d}@{label}" for d in frame["dim_value"]],
            )
        )
    return pd.concat(parts, ignore_index=True)


@register("M03", "门诊次均费用", "门诊", "元")
def calc_outpatient_avg_cost(start_date, end_date, granularity="month", *, engine=None, dept=None) -> pd.DataFrame:
    """门诊次均费用 = 门诊费用合计（登记口径）÷ 门诊人次。"""
    frame = _prepared(start_date, end_date, granularity, engine=engine, dept=dept)
    if frame.empty:
        return frame
    return _emit("M03", frame, _ratio(frame["op_fee_sum"], frame["op_visit_cnt"]))


@register("M04", "门诊预约率", "门诊", "%")
def calc_appointment_rate(start_date, end_date, granularity="month", *, engine=None, dept=None) -> pd.DataFrame:
    """预约率：数据集无预约标识字段 -> NULL / PENDING（口径已定义，数据源待补充）。"""
    frame = _prepared(start_date, end_date, granularity, engine=engine, dept=dept)
    if frame.empty:
        return frame
    return _pending("M04", frame)


@register("M05", "门诊退号率", "门诊", "%")
def calc_refund_rate(start_date, end_date, granularity="month", *, engine=None, dept=None) -> pd.DataFrame:
    """退号率：数据集无退号标识字段 -> NULL / PENDING。"""
    frame = _prepared(start_date, end_date, granularity, engine=engine, dept=dept)
    if frame.empty:
        return frame
    return _pending("M05", frame)


@register("M06", "门急诊人次", "门诊", "人次")
def calc_emergency_visit_total(start_date, end_date, granularity="month", *, engine=None, dept=None) -> pd.DataFrame:
    """门急诊人次：门诊表含全部号别，等于门诊人次口径。"""
    frame = _prepared(start_date, end_date, granularity, engine=engine, dept=dept)
    if frame.empty:
        return frame
    return _emit("M06", frame, frame["op_visit_cnt"])


@register("M07", "门诊收入", "门诊", "元")
def calc_outpatient_revenue(start_date, end_date, granularity="month", *, engine=None, dept=None) -> pd.DataFrame:
    """门诊收入（流水口径）：visit_type=门诊 的收费合计。"""
    frame = _prepared(start_date, end_date, granularity, engine=engine, dept=dept)
    if frame.empty:
        return frame
    return _emit("M07", frame, frame["op_charge_amt"].round(2))


# ---------------------------------------------------------------- 住院主题
@register("M08", "出院人次", "住院", "人次")
def calc_inpatient_discharge(start_date, end_date, granularity="month", *, engine=None, dept=None) -> pd.DataFrame:
    """出院人次：按出院日期归属。"""
    frame = _prepared(start_date, end_date, granularity, engine=engine, dept=dept)
    if frame.empty:
        return frame
    return _emit("M08", frame, frame["ip_discharge_cnt"])


@register("M09", "入院人次", "住院", "人次")
def calc_inpatient_admit(start_date, end_date, granularity="month", *, engine=None, dept=None) -> pd.DataFrame:
    """入院人次：按入院日期归属。"""
    frame = _prepared(start_date, end_date, granularity, engine=engine, dept=dept)
    if frame.empty:
        return frame
    return _emit("M09", frame, frame["ip_admit_cnt"])


@register("M10", "实际占用总床日数", "住院", "床日")
def calc_bed_days(start_date, end_date, granularity="month", *, engine=None, dept=None) -> pd.DataFrame:
    """实际占用总床日数 = Σ 住院天数（已出院患者）。"""
    frame = _prepared(start_date, end_date, granularity, engine=engine, dept=dept)
    if frame.empty:
        return frame
    return _emit("M10", frame, frame["bed_days"])


@register("M11", "床位使用率", "住院", "%")
def calc_bed_usage_rate(start_date, end_date, granularity="month", *, engine=None, dept=None) -> pd.DataFrame:
    """床位使用率 = 实际占用床日 ÷ (开放床位 × 统计天数) × 100。"""
    frame = _prepared(start_date, end_date, granularity, engine=engine, dept=dept)
    if frame.empty:
        return frame
    return _emit("M11", frame, _ratio(frame["bed_days"], frame["bed_cnt"], 100))


@register("M12", "平均住院日", "住院", "天")
def calc_avg_stay_days(start_date, end_date, granularity="month", *, engine=None, dept=None) -> pd.DataFrame:
    """平均住院日 = 实际占用床日 ÷ 出院人次。"""
    frame = _prepared(start_date, end_date, granularity, engine=engine, dept=dept)
    if frame.empty:
        return frame
    return _emit("M12", frame, _ratio(frame["bed_days"], frame["ip_discharge_cnt"]))


@register("M13", "住院次均费用", "住院", "元")
def calc_inpatient_avg_cost(start_date, end_date, granularity="month", *, engine=None, dept=None) -> pd.DataFrame:
    """住院次均费用 = 住院费用合计（登记口径）÷ 出院人次。"""
    frame = _prepared(start_date, end_date, granularity, engine=engine, dept=dept)
    if frame.empty:
        return frame
    return _emit("M13", frame, _ratio(frame["ip_fee_sum"], frame["ip_discharge_cnt"]))


@register("M14", "手术占比", "住院", "%")
def calc_surgery_ratio(start_date, end_date, granularity="month", *, engine=None, dept=None) -> pd.DataFrame:
    """手术占比 = 含手术费记录的住院就诊数 ÷ 出院人次 × 100（源数据无手术系统标识时按手术费近似）。"""
    frame = _prepared(start_date, end_date, granularity, engine=engine, dept=dept)
    if frame.empty:
        return frame
    return _emit("M14", frame, _ratio(frame["ip_ss_visit_cnt"], frame["ip_discharge_cnt"], 100))


@register("M15", "住院收入", "住院", "元")
def calc_inpatient_revenue(start_date, end_date, granularity="month", *, engine=None, dept=None) -> pd.DataFrame:
    """住院收入（流水口径）：visit_type=住院 的收费合计。"""
    frame = _prepared(start_date, end_date, granularity, engine=engine, dept=dept)
    if frame.empty:
        return frame
    return _emit("M15", frame, frame["ip_charge_amt"].round(2))


# ---------------------------------------------------------------- 收入主题
@register("M16", "医疗收入合计", "收入", "元")
def calc_total_revenue(start_date, end_date, granularity="month", *, engine=None, dept=None) -> pd.DataFrame:
    """医疗收入合计 = 门诊收入 + 住院收入（流水口径）。"""
    frame = _prepared(start_date, end_date, granularity, engine=engine, dept=dept)
    if frame.empty:
        return frame
    return _emit("M16", frame, frame["charge_amt_sum"].round(2))


@register("M17", "药品收入", "收入", "元")
def calc_drug_revenue(start_date, end_date, granularity="month", *, engine=None, dept=None) -> pd.DataFrame:
    """药品收入 = 西药费 + 中成药费（流水口径）。"""
    frame = _prepared(start_date, end_date, granularity, engine=engine, dept=dept)
    if frame.empty:
        return frame
    return _emit("M17", frame, frame["charge_drug_amt"].round(2))


@register("M18", "耗材收入", "收入", "元")
def calc_consumable_revenue(start_date, end_date, granularity="month", *, engine=None, dept=None) -> pd.DataFrame:
    """耗材收入 = 材料费（流水口径）。"""
    frame = _prepared(start_date, end_date, granularity, engine=engine, dept=dept)
    if frame.empty:
        return frame
    return _emit("M18", frame, frame["charge_consumable_amt"].round(2))


@register("M19", "药占比", "收入", "%")
def calc_drug_ratio(start_date, end_date, granularity="month", *, engine=None, dept=None) -> pd.DataFrame:
    """药占比（财务口径，默认）= 财务药品收入 ÷ 财务收入 × 100。"""
    frame = _prepared(start_date, end_date, granularity, engine=engine, dept=dept)
    if frame.empty:
        return frame
    return _emit("M19", frame, _ratio(frame["fin_drug_revenue"], frame["fin_revenue"], 100))


@register("M20", "耗占比", "收入", "%")
def calc_consumable_ratio(start_date, end_date, granularity="month", *, engine=None, dept=None) -> pd.DataFrame:
    """耗占比（财务口径，默认）= 财务耗材收入 ÷ 财务收入 × 100。"""
    frame = _prepared(start_date, end_date, granularity, engine=engine, dept=dept)
    if frame.empty:
        return frame
    return _emit("M20", frame, _ratio(frame["fin_consumable_revenue"], frame["fin_revenue"], 100))


@register("M21", "检查检验收入占比", "收入", "%")
def calc_exam_lab_ratio(start_date, end_date, granularity="month", *, engine=None, dept=None) -> pd.DataFrame:
    """检查检验收入占比 = (检查费 + 检验费) ÷ 医疗收入 × 100（流水口径）。"""
    frame = _prepared(start_date, end_date, granularity, engine=engine, dept=dept)
    if frame.empty:
        return frame
    return _emit("M21", frame, _ratio(frame["charge_exam_lab_amt"], frame["charge_amt_sum"], 100))


@register("M22", "医疗服务性收入占比", "收入", "%")
def calc_service_ratio(start_date, end_date, granularity="month", *, engine=None, dept=None) -> pd.DataFrame:
    """医疗服务性收入占比 = (治疗+手术+床位+护理) ÷ 医疗收入 × 100。"""
    frame = _prepared(start_date, end_date, granularity, engine=engine, dept=dept)
    if frame.empty:
        return frame
    return _emit("M22", frame, _ratio(frame["charge_service_amt"], frame["charge_amt_sum"], 100))


# ---------------------------------------------------------------- 病种主题
@register("M23", "DRG 入组率", "病种", "%")
def calc_drg_group_rate(start_date, end_date, granularity="month", *, engine=None, dept=None) -> pd.DataFrame:
    """DRG 入组率 = 成功匹配 DRG 组的出院病例数 ÷ 出院人次 × 100（模拟分组）。"""
    frame = _prepared(start_date, end_date, granularity, engine=engine, dept=dept)
    if frame.empty:
        return frame
    return _emit("M23", frame, _ratio(frame["drg_cases"], frame["ip_discharge_cnt"], 100))


@register("M24", "CMI 病例组合指数", "病种", "指数")
def calc_cmi(start_date, end_date, granularity="month", *, engine=None, dept=None) -> pd.DataFrame:
    """CMI = Σ(DRG 权重 RW × 例数) ÷ 入组病例数。"""
    frame = _prepared(start_date, end_date, granularity, engine=engine, dept=dept)
    if frame.empty:
        return frame
    return _emit("M24", frame, _ratio(frame["drg_rw_sum"], frame["drg_cases"]))


@register("M25", "费用消耗指数", "病种", "指数")
def calc_fee_index(start_date, end_date, granularity="month", *, engine=None, dept=None) -> pd.DataFrame:
    """费用消耗指数 = 实际费用 ÷ 期望费用，期望费用 = 全院次均费用 × 该组 RW 合计。"""
    frame = _prepared(start_date, end_date, granularity, engine=engine, dept=dept)
    if frame.empty:
        return frame
    all_rows = frame.loc[frame["dim_value"] == "ALL", ["period_date", "ip_fee_sum", "ip_discharge_cnt"]]
    avg_fee = {
        row.period_date: (float(row.ip_fee_sum) / float(row.ip_discharge_cnt) if row.ip_discharge_cnt else None)
        for row in all_rows.itertuples()
    }
    expected = frame["drg_rw_sum"] * frame["period_date"].map(avg_fee)
    return _emit("M25", frame, _ratio(frame["ip_fee_sum"], expected))


@register("M26", "时间消耗指数", "病种", "指数")
def calc_time_index(start_date, end_date, granularity="month", *, engine=None, dept=None) -> pd.DataFrame:
    """时间消耗指数 = 实际床日 ÷ 期望床日，期望床日 = 全院平均住院日 × 该组 RW 合计。"""
    frame = _prepared(start_date, end_date, granularity, engine=engine, dept=dept)
    if frame.empty:
        return frame
    all_rows = frame.loc[frame["dim_value"] == "ALL", ["period_date", "bed_days", "ip_discharge_cnt"]]
    avg_days = {
        row.period_date: (float(row.bed_days) / float(row.ip_discharge_cnt) if row.ip_discharge_cnt else None)
        for row in all_rows.itertuples()
    }
    expected = frame["drg_rw_sum"] * frame["period_date"].map(avg_days)
    return _emit("M26", frame, _ratio(frame["bed_days"], expected))


@register("M27", "低风险组死亡率", "病种", "%")
def calc_low_risk_mortality(start_date, end_date, granularity="month", *, engine=None, dept=None) -> pd.DataFrame:
    """低风险组死亡率：数据集无死亡标识与风险分级字段 -> NULL / PENDING。"""
    frame = _prepared(start_date, end_date, granularity, engine=engine, dept=dept)
    if frame.empty:
        return frame
    return _pending("M27", frame)


# ---------------------------------------------------------------- 资源效率与患者服务
@register("M28", "医师人均门诊人次", "资源效率", "人次")
def calc_op_per_doctor(start_date, end_date, granularity="month", *, engine=None, dept=None) -> pd.DataFrame:
    """医师人均门诊人次 = 门诊人次 ÷ 在岗医师数（取 dim_department.doctor_cnt，模拟维护值）。"""
    frame = _prepared(start_date, end_date, granularity, engine=engine, dept=dept)
    if frame.empty:
        return frame
    return _emit("M28", frame, _ratio(frame["op_visit_cnt"], frame["staff_doctor"]))


@register("M29", "床护比", "资源效率", "床/人")
def calc_bed_nurse_ratio(start_date, end_date, granularity="month", *, engine=None, dept=None) -> pd.DataFrame:
    """床护比 = 平均开放床位数 ÷ 在岗护士数（取 dim_department.nurse_cnt，模拟维护值）。"""
    frame = _prepared(start_date, end_date, granularity, engine=engine, dept=dept)
    if frame.empty:
        return frame
    # 床位数为日快照：Σ床位 ÷ 统计天数 = 平均开放床位数
    days = pd.to_numeric(frame["stat_days"], errors="coerce").where(lambda s: s > 0)
    avg_beds = pd.to_numeric(frame["bed_cnt"], errors="coerce").divide(days)
    return _emit("M29", frame, _ratio(avg_beds, frame["staff_nurse"]))


@register("M30", "百元医疗收入耗材消耗", "资源效率", "元")
def calc_hundred_yuan_consumable(start_date, end_date, granularity="month", *, engine=None, dept=None) -> pd.DataFrame:
    """百元医疗收入耗材消耗 = 耗材收入 ÷ 医疗收入 × 100（流水口径）。"""
    frame = _prepared(start_date, end_date, granularity, engine=engine, dept=dept)
    if frame.empty:
        return frame
    return _emit("M30", frame, _ratio(frame["charge_consumable_amt"], frame["charge_amt_sum"], 100))


@register("M31", "患者复诊率", "患者服务", "%")
def calc_repeat_visit_rate(start_date, end_date, granularity="month", *, engine=None, dept=None) -> pd.DataFrame:
    """患者复诊率 = 复诊人次 ÷ 门诊人次 × 100。

    复诊口径按**统计窗口**计算：同一患者在窗口内门诊就诊 ≥2 次，第 2 次起计复诊人次。
    该指标需按窗口重算，故直接读 DWD 门诊明细（而非 DWS 日汇总的简单求和）。
    """
    from etl.config.dwd_schema import DWD_TABLES

    eng = engine or get_engine()
    start = normalize_batch_date(start_date)
    end = normalize_batch_date(end_date)
    op = read_table_df(eng, DWD_TABLES["dwd_outpatient_visit_detail"])
    if op.empty:
        return pd.DataFrame()
    op = op.copy()
    op["stat_date"] = pd.to_datetime(op["visit_date"], errors="coerce").dt.date
    op = op.loc[(op["stat_date"] >= start) & (op["stat_date"] <= end)]
    if dept:
        op = op.loc[op["dept_code"] == dept]
    if op.empty:
        return pd.DataFrame()

    op["period_date"] = _period_end(op["stat_date"], granularity, end)
    op["granularity"] = granularity
    # 首诊/复诊判定：同一患者在同一统计窗口内按就诊日期排序，首次为首诊，其后均计复诊
    op = op.sort_values(["period_date", "patient_id", "stat_date", "visit_id"])
    op["_rank"] = op.groupby(["period_date", "patient_id"]).cumcount() + 1
    op["_repeat"] = (op["_rank"] > 1).astype(int)

    def _agg(keys: list[str]) -> pd.DataFrame:
        return op.groupby(keys, as_index=False).agg(visits=("visit_id", "nunique"), repeats=("_repeat", "sum"))

    dept_grp = _agg(["dept_code", "period_date", "granularity"]).rename(columns={"dept_code": "dim_value"})
    all_grp = _agg(["period_date", "granularity"])
    all_grp["dim_value"] = "ALL"
    frame = pd.concat([dept_grp, all_grp], ignore_index=True)
    frame = frame.sort_values(["dim_value", "period_date"]).reset_index(drop=True)
    return _emit("M31", frame, _ratio(frame["repeats"], frame["visits"], 100))


@register("M32", "检验阳性率", "患者服务", "%")
def calc_lis_positive_rate(start_date, end_date, granularity="month", *, engine=None, dept=None) -> pd.DataFrame:
    """检验阳性率 = 异常类检验报告数 ÷ 检验报告总数 × 100。"""
    frame = _prepared(start_date, end_date, granularity, engine=engine, dept=dept)
    if frame.empty:
        return frame
    return _emit("M32", frame, _ratio(frame["lis_abnormal_cnt"], frame["lis_report_cnt"], 100))


@register("M33", "收入增长率", "收入", "%")
def calc_revenue_growth(start_date, end_date, granularity="month", *, engine=None, dept=None) -> pd.DataFrame:
    """收入增长率（环比）= (本期收入 − 上期收入) ÷ 上期收入 × 100；无上期时记 NULL/PENDING。"""
    frame = _prepared(start_date, end_date, granularity, engine=engine, dept=dept)
    if frame.empty:
        return frame
    frame = frame.copy()
    frame["prev_amt"] = frame.groupby("dim_value")["charge_amt_sum"].shift(1)
    values = _ratio(frame["charge_amt_sum"] - frame["prev_amt"], frame["prev_amt"], 100)
    status = ["OK" if pd.notna(v) else "PENDING" for v in values]
    out = _emit("M33", frame, values)
    out["data_status"] = status
    return out


# ---------------------------------------------------------------- 批量计算与回刷
INDICATOR_COLUMNS = [
    "metric_code",
    "metric_name",
    "theme",
    "dim_value",
    "granularity",
    "stat_date",
    "metric_value",
    "unit",
    "data_status",
    "metric_version",
    "calc_batch_id",
    "etl_load_time",
]


def compute_all(
    start_date: str,
    end_date: str,
    granularity: str = "month",
    *,
    engine: Engine | None = None,
    dept: str | None = None,
    metrics: Sequence[str] | None = None,
) -> pd.DataFrame:
    """按注册表批量计算全部指标，返回合并后的结果 DataFrame（不落库）。"""
    eng = engine or get_engine()
    codes = list(metrics) if metrics else list(REGISTRY)
    frames: list[pd.DataFrame] = []
    failures: list[str] = []
    for code in codes:
        meta = REGISTRY.get(code)
        if meta is None:
            raise KeyError(f"未注册的指标：{code}")
        started = time.perf_counter()
        try:
            df = meta["func"](start_date, end_date, granularity, engine=eng, dept=dept)
        except Exception as exc:  # noqa: BLE001 - 单指标失败不阻断其余指标
            failures.append(f"{code} {meta['name']}: {type(exc).__name__}: {exc}")
            _log(f"{code} {meta['name']} FAILED {type(exc).__name__}: {exc}")
            continue
        duration = (time.perf_counter() - started) * 1000
        if df is None or df.empty:
            failures.append(f"{code} {meta['name']}: 无数据产出")
            _log(f"{code} {meta['name']} EMPTY 粒度={granularity}")
            continue
        frames.append(df)
        ok = int((df["data_status"] == "OK").sum())
        pending = int((df["data_status"] == "PENDING").sum())
        _log(f"{code} {meta['name']} rows={len(df)} OK={ok} PENDING={pending} cost={duration:.0f}ms")
    if failures:
        print(f"  [WARN] {len(failures)} 项指标计算失败（详见 logs/indicator_run.log）：")
        for failure in failures:
            print(f"    · {failure}")
    if not frames:
        return pd.DataFrame(columns=INDICATOR_COLUMNS)
    return pd.concat(frames, ignore_index=True)


def _log(message: str) -> None:
    """指标运行日志（追加写入 logs/indicator_run.log）。"""
    INDICATOR_LOG.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with INDICATOR_LOG.open("a", encoding="utf-8") as fp:
        fp.write(f"[{stamp}] {message}\n")


def _pythonize(value: Any) -> Any:
    from etl.config.loader import pythonize

    return pythonize(value)


def write_indicator_result(
    frame: pd.DataFrame,
    start_date: str,
    end_date: str,
    granularity: str,
    *,
    engine: Engine | None = None,
    batch_date: date | str | None = None,
) -> int:
    """把指标结果写入 ads_indicator_result（先删同粒度同期旧结果，保证幂等）。"""
    eng = engine or get_engine()
    bd = normalize_batch_date(batch_date)
    start = normalize_batch_date(start_date)
    end = normalize_batch_date(end_date)

    payload = frame.copy()
    payload["metric_version"] = "V1.0"
    payload["calc_batch_id"] = batch_id_of(bd)
    payload["etl_load_time"] = datetime.now()
    payload = payload[[c for c in INDICATOR_COLUMNS if c in payload.columns]]

    allowed = {c.name for c in ads_indicator_result.columns}
    records = [
        {k: _pythonize(v) for k, v in row.items() if k in allowed} for row in payload.to_dict("records")
    ]

    with eng.begin() as conn:
        deleted = conn.execute(
            delete(ads_indicator_result).where(
                ads_indicator_result.c.granularity == granularity,
                ads_indicator_result.c.stat_date >= start,
                ads_indicator_result.c.stat_date <= end,
            )
        ).rowcount
        if records:
            conn.execute(ads_indicator_result.insert(), records)
    if deleted:
        print(f"    · ads_indicator_result: 清理同粒度同期旧结果 {deleted} 行")
    return len(records)


def run_indicators(
    start_date: str,
    end_date: str,
    granularity: str = "month",
    *,
    engine: Engine | None = None,
    dept: str | None = None,
    metrics: Sequence[str] | None = None,
    batch_date: date | str | None = None,
) -> dict[str, Any]:
    """按注册表批量计算并写入 ads_indicator_result，返回执行摘要。"""
    eng = engine or get_engine()
    bd = normalize_batch_date(batch_date)
    print(f"[指标] 统计期 {start_date} ~ {end_date}，粒度 {granularity}，批次 {batch_id_of(bd)}")
    frame = compute_all(start_date, end_date, granularity, engine=eng, dept=dept, metrics=metrics)
    if frame.empty:
        print("[指标] 未产出任何指标结果")
        return {"rows": 0, "metrics": 0, "pending": 0, "granularity": granularity}
    rows = write_indicator_result(frame, start_date, end_date, granularity, engine=eng, batch_date=bd)
    ok = int((frame["data_status"] == "OK").sum())
    pending = int((frame["data_status"] == "PENDING").sum())
    metrics = int(frame["metric_code"].nunique())
    print(
        f"[指标] 完成：{metrics} 项指标 / {rows} 行结果（正常 {ok} / 待补充 {pending}），"
        f"写入 ads_indicator_result"
    )
    return {
        "rows": rows,
        "metrics": metrics,
        "ok": ok,
        "pending": pending,
        "granularity": granularity,
        "start_date": str(start_date),
        "end_date": str(end_date),
    }


def rerun(
    date_range: Sequence[str] | None = None,
    granularity: str = "month",
    *,
    engine: Engine | None = None,
    batch_date: date | str | None = None,
) -> dict[str, Any]:
    """指定区间回刷指标（先删后插，幂等）。"""
    if date_range:
        start, end = date_range[0], date_range[1]
    else:
        from etl.config.baseline import STAT_PERIOD

        start, end = STAT_PERIOD
    print(f"[回刷] 区间 {start} ~ {end}，粒度 {granularity}（先删后插，幂等）")
    summary = run_indicators(start, end, granularity, engine=engine, batch_date=batch_date)
    summary["rerun_range"] = [start, end]
    print(f"[回刷] 完成，共 {summary['rows']} 行")
    return summary


# ---------------------------------------------------------------- 手工 SQL 对账
RECONCILE_SQL: dict[str, tuple[str, str]] = {
    # 指标编码 -> (说明, 独立手工 SQL：直接扫 DWD/ODS，不复用指标函数)
    "M01": (
        "门诊人次",
        "SELECT COUNT(DISTINCT visit_id) FROM dwd_outpatient_visit_detail"
        " WHERE visit_date >= :start AND visit_date <= :end",
    ),
    "M03": (
        "门诊次均费用",
        "SELECT AVG(fee_amount) FROM dwd_outpatient_visit_detail"
        " WHERE visit_date >= :start AND visit_date <= :end",
    ),
    "M08": (
        "出院人次",
        "SELECT COUNT(DISTINCT visit_id) FROM dwd_inpatient_visit_detail"
        " WHERE discharge_date >= :start AND discharge_date <= :end",
    ),
    "M10": (
        "实际占用总床日数",
        "SELECT SUM(stay_days) FROM dwd_inpatient_visit_detail"
        " WHERE discharge_date >= :start AND discharge_date <= :end",
    ),
    "M12": (
        "平均住院日",
        "SELECT SUM(stay_days) * 1.0 / COUNT(*) FROM dwd_inpatient_visit_detail"
        " WHERE discharge_date >= :start AND discharge_date <= :end",
    ),
    "M16": (
        "医疗收入合计",
        "SELECT SUM(amount) FROM dwd_charge_detail WHERE fee_date >= :start AND fee_date <= :end",
    ),
    "M19": (
        "药占比（财务口径）",
        "SELECT SUM(drug_revenue) * 100.0 / SUM(revenue) FROM dwd_finance_daily_detail"
        " WHERE stat_date >= :start AND stat_date <= :end",
    ),
    "M24": (
        "CMI",
        "SELECT SUM(rw) * 1.0 / COUNT(*) FROM dwd_inpatient_visit_detail"
        " WHERE discharge_date >= :start AND discharge_date <= :end",
    ),
    "M31": (
        "患者复诊率",
        "SELECT (SUM(c) - COUNT(*)) * 100.0 / SUM(c) FROM ("
        "  SELECT patient_id, COUNT(*) AS c FROM dwd_outpatient_visit_detail"
        "   WHERE visit_date >= :start AND visit_date <= :end GROUP BY patient_id) t",
    ),
    "M32": (
        "检验阳性率",
        "SELECT SUM(CASE WHEN result_flag = '异常' THEN 1 ELSE 0 END) * 100.0 / COUNT(*)"
        " FROM dwd_lis_report_detail WHERE report_date >= :start AND report_date <= :end",
    ),
}


def _stored_value(
    code: str,
    granularity: str,
    *,
    engine: Engine,
    dim_value: str = "ALL",
    stat_date: date | None = None,
) -> float | None:
    """读取指标结果表中某指标的值（可指定统计日期，避免多期数据取错行）。"""
    stmt = select(ads_indicator_result.c.metric_value).where(
        ads_indicator_result.c.metric_code == code,
        ads_indicator_result.c.dim_value == dim_value,
        ads_indicator_result.c.granularity == granularity,
    )
    if stat_date is not None:
        stmt = stmt.where(ads_indicator_result.c.stat_date == stat_date)
    with engine.connect() as conn:
        value = conn.execute(stmt.order_by(ads_indicator_result.c.stat_date.desc())).first()
    if value is None or value[0] is None:
        return None
    return float(value[0])


def reconcile_indicators(
    start_date: str,
    end_date: str,
    *,
    engine: Engine | None = None,
    granularity: str = "period",
    output_dir: str | None = None,
) -> dict[str, Any]:
    """抽样 10 项指标，用独立手工 SQL 复算并与 ads_indicator_result 比对（误差应为 0）。"""
    eng = engine or get_engine()
    start = str(normalize_batch_date(start_date))
    end = normalize_batch_date(end_date)
    records: list[dict[str, Any]] = []
    max_error = 0.0

    for code, (desc, sql) in RECONCILE_SQL.items():
        with eng.connect() as conn:
            manual = conn.execute(text(sql), {"start": start, "end": str(end)}).scalar()
        stored = _stored_value(
            code, granularity, engine=eng, dim_value="ALL", stat_date=end if granularity == "period" else None
        )

        manual_value = float(manual) if manual is not None else None
        stored_value = float(stored) if stored is not None else None
        if manual_value is None or stored_value is None:
            error = None
        else:
            error = abs(manual_value - stored_value)
            max_error = max(max_error, error)
        records.append(
            {
                "metric_code": code,
                "metric_name": desc,
                "manual_sql_value": None if manual_value is None else round(manual_value, 4),
                "stored_value": None if stored_value is None else round(stored_value, 4),
                "abs_error": None if error is None else round(error, 6),
                "passed": (error is not None and error <= 0.01),
            }
        )

    passed = sum(1 for r in records if r["passed"])
    report = {
        "report_meta": {
            "stage": "阶段三 指标计算对账",
            "stat_period": [start, str(end)],
            "granularity": granularity,
            "generate_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "method": "独立手工 SQL 复算 vs ads_indicator_result（不走指标函数链路）",
        },
        "summary": {
            "sampled": len(records),
            "passed": passed,
            "failed": len(records) - passed,
            "max_abs_error": round(max_error, 6),
            "all_zero_error": max_error <= 0.01,
        },
        "records": records,
    }

    out_dir = LOG_DIR if output_dir is None else __import__("pathlib").Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_file = out_dir / f"indicator_reconcile_{normalize_batch_date(end_date):%Y%m%d}.json"
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n[对账] 抽样 {len(records)} 项指标，通过 {passed} 项，最大绝对误差 {max_error:.6f}")
    for r in records:
        flag = "OK  " if r["passed"] else "FAIL"
        print(
            f"  [{flag}] {r['metric_code']} {r['metric_name']:<18} "
            f"手工 SQL={r['manual_sql_value']} / 结果表={r['stored_value']} / 误差={r['abs_error']}"
        )
    print(f"[对账] 比对记录已留存：{report_file}")
    return report


def verify_indicators(
    start_date: str,
    end_date: str,
    granularity: str = "period",
    *,
    engine: Engine | None = None,
) -> list[dict[str, Any]]:
    """校验指标结果表：指标项数、唯一键、待补充指标、基线命中情况。"""
    from etl.config.baseline import METRIC_BASELINE

    eng = engine or get_engine()
    start = normalize_batch_date(start_date)
    end = normalize_batch_date(end_date)
    checks: list[dict[str, Any]] = []

    with eng.connect() as conn:
        total = int(
            conn.execute(
                select(func.count()).select_from(ads_indicator_result).where(
                    ads_indicator_result.c.granularity == granularity
                )
            ).scalar_one()
        )
        distinct_metrics = int(
            conn.execute(
                select(func.count(func.distinct(ads_indicator_result.c.metric_code))).where(
                    ads_indicator_result.c.granularity == granularity
                )
            ).scalar_one()
        )
        dup = conn.execute(
            text(
                "SELECT COUNT(*) FROM (SELECT metric_code, dim_value, granularity, stat_date, COUNT(*) c"
                " FROM ads_indicator_result GROUP BY 1,2,3,4 HAVING c > 1) t"
            )
        ).scalar()

    checks.append(
        {
            "check": "指标项数≥30",
            "expected": ">=30",
            "actual": distinct_metrics,
            "ok": distinct_metrics >= 30,
            "detail": f"{distinct_metrics} 项指标 / {total} 行结果",
        }
    )
    checks.append(
        {
            "check": "结果表唯一键无重复",
            "expected": 0,
            "actual": int(dup or 0),
            "ok": int(dup or 0) == 0,
            "detail": "指标编码+维度值+粒度+统计日期",
        }
    )

    # 基线命中（全院、统计期粒度）
    baseline_map = {
        "M01": METRIC_BASELINE["M01"],
        "M03": METRIC_BASELINE["M03"],
        "M10": METRIC_BASELINE["M10"],
        "M11": METRIC_BASELINE["M11"],
        "M12": METRIC_BASELINE["M12"],
        "M16": METRIC_BASELINE["M16"],
        "M19": METRIC_BASELINE["M19"],
        "M20": METRIC_BASELINE["M20"],
        "M24": METRIC_BASELINE["M24"],
        "M31": METRIC_BASELINE["M31"],
        "M32": METRIC_BASELINE["M32"],
    }
    for code, expected in baseline_map.items():
        actual = _stored_value(
            code, granularity, engine=eng, dim_value="ALL",
            stat_date=end if granularity == "period" else None,
        )
        if actual is None:
            ok = False
            detail = "无结果"
        else:
            ok = abs(actual - float(expected)) <= 0.01
            detail = f"实际 {actual:,.4f} / 基线 {expected}"
        checks.append(
            {"check": f"基线命中·{code}", "expected": expected, "actual": actual, "ok": ok, "detail": detail}
        )
    return checks


if __name__ == "__main__":  # 手工自检：python -m etl.jobs.ads_indicators
    from etl.config.baseline import STAT_PERIOD
    from etl.config.settings import DEFAULT_BATCH_DATE

    rerun(STAT_PERIOD, "month", batch_date=DEFAULT_BATCH_DATE)
    print("\n指标校验：")
    for item in verify_indicators(STAT_PERIOD[0], STAT_PERIOD[1], "month"):
        print(f"  [{'OK  ' if item['ok'] else 'FAIL'}] {item['check']:<16} {item['detail']}")
    reconcile_indicators(STAT_PERIOD[0], STAT_PERIOD[1], granularity="month")
