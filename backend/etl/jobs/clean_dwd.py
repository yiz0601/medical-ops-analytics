"""DWD 分层清洗与加工（阶段二 · 步骤 3）。

四个可复用清洗算子 + 两条执行入口：

    dedupe(df, keys)                         按业务主键去重（保留最后一条）
    fill_missing(df, strategy)               缺失值填充（众数/均值/中位数/常量）
    standardize_codes(df, mapping, column)   字典编码映射（科室/号别/费别/病种）
    mask_privacy(df, columns)                隐私字段脱敏（姓名/身份证/手机号）
    write_dwd(table, batch_date)             单表加工：ODS 读取 -> 算子流水线 -> 写 DWD
    run_clean_all(batch_date)                逐表加工全部 DWD 表，返回 {DWD 表名: 行数}
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any, Mapping, Sequence

import pandas as pd
from sqlalchemy.engine import Engine

from etl.config.dicts import (
    DEPT_NAME,
    DISEASE_NAME,
    DRG_CODE,
    DRG_RW,
    FEE_CLASS,
    LIS_RESULT_FLAG,
    VISIT_TYPE_DICT,
    age_group_of,
)
from etl.config.dwd_schema import DWD_TABLES
from etl.config.loader import load_by_batch, read_table_df
from etl.config.ods_schema import ODS_TABLES
from etl.config.settings import get_engine, normalize_batch_date


# ---------------------------------------------------------------- 步骤 3-2：清洗算子
def dedupe(df: pd.DataFrame, keys: Sequence[str]) -> pd.DataFrame:
    """按业务主键去重（保留最后一条），并打印删除行数。"""
    cols = [k for k in keys if k in df.columns]
    if not cols:
        return df.reset_index(drop=True)
    before = len(df)
    out = df.drop_duplicates(subset=cols, keep="last").reset_index(drop=True)
    dropped = before - len(out)
    if dropped:
        print(f"    · 去重[{','.join(cols)}] 删除 {dropped} 行")
    return out


def fill_missing(df: pd.DataFrame, strategy: Mapping[str, Any] | None) -> pd.DataFrame:
    """缺失值填充。

    strategy 形如 {"gender": "未知", "age": "mean", "dept_code": "mode"}：
    取值为 "mode"/"mean"/"median" 时按统计量填充，其余视为常量填充。
    """
    for col, how in (strategy or {}).items():
        if col not in df.columns:
            continue
        series = df[col]
        missing = int(series.isna().sum())
        if missing == 0:
            continue
        if isinstance(how, str) and how in {"mode", "mean", "median"}:
            if how == "mode":
                mode = series.mode(dropna=True)
                fill_value = mode.iloc[0] if not mode.empty else None
            else:
                fill_value = series.mean() if how == "mean" else series.median()
        else:
            fill_value = how
        if fill_value is None or (isinstance(fill_value, float) and math.isnan(fill_value)):
            continue
        df[col] = series.fillna(fill_value)
        print(f"    · 填充[{col}] {missing} 行 -> {fill_value}")
    return df


def standardize_codes(
    df: pd.DataFrame,
    mapping: Mapping[Any, Any],
    column: str,
    *,
    new_column: str | None = None,
    default: str = "UNKNOWN",
) -> pd.DataFrame:
    """按字典映射标准编码/名称。

    new_column 为空时覆盖原列（源编码 -> 标准编码）；否则新增列并保留原列。
    未命中映射的取值统一置为 default，并打印未命中行数。
    """
    if column not in df.columns:
        return df
    source = df[column]
    mapped = source.map(lambda v: mapping.get(v, default) if pd.notna(v) else default)
    unmapped_mask = ~source.isin(list(mapping.keys()))
    unmapped = int(unmapped_mask.sum())
    if unmapped:
        print(f"    · 字典映射[{column}] 未命中 {unmapped} 行 -> {default}")
    df[new_column or column] = mapped
    return df


# ---------------------------------------------------------------- 隐私脱敏
def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    if value is pd.NA or value is pd.NaT:
        return ""
    return str(value).strip()


def mask_name(value: Any) -> str | None:
    """姓名脱敏：保留首字，其余掩码（张秀兰 -> 张**）。"""
    text = _as_text(value)
    if not text:
        return None
    return text[0] + "**"


def mask_id_card(value: Any) -> str | None:
    """身份证脱敏：保留前 6 位与后 4 位（11018451848947609 -> 110184*********7609）。"""
    text = _as_text(value)
    if not text:
        return None
    if len(text) <= 10:
        return text[:3] + "*" * max(len(text) - 3, 0)
    return text[:6] + "*" * (len(text) - 10) + text[-4:]


def mask_phone(value: Any) -> str | None:
    """手机号脱敏：保留前 3 位与后 4 位（13873577907 -> 138****7907）。"""
    text = _as_text(value)
    if not text:
        return None
    if len(text) <= 7:
        return text[:3] + "*" * max(len(text) - 3, 0)
    return text[:3] + "****" + text[-4:]


def _mask_generic(value: Any) -> str | None:
    text = _as_text(value)
    if not text:
        return None
    if len(text) <= 2:
        return "*" * len(text)
    return text[0] + "*" * (len(text) - 2) + text[-1]


def mask_privacy(df: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    """按列名语义自动选择脱敏规则，批量脱敏。"""
    for col in columns:
        if col not in df.columns:
            continue
        name = col.lower()
        if "id_card" in name or "idcard" in name:
            func = mask_id_card
        elif "phone" in name or "mobile" in name or "tel" in name:
            func = mask_phone
        elif "name" in name:
            func = mask_name
        else:
            func = _mask_generic
        before = df[col].notna().sum()
        df[col] = df[col].map(func)
        print(f"    · 脱敏[{col}] {int(before)} 行")
    return df


# ---------------------------------------------------------------- 各表加工流水线
def _pipeline_outpatient(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(
        columns={
            "patient_name": "patient_name_masked",
            "id_card": "id_card_masked",
            "phone": "phone_masked",
        }
    )
    df = dedupe(df, ["visit_id"])
    df = mask_privacy(df, ["patient_name_masked", "id_card_masked", "phone_masked"])
    df = fill_missing(df, {"gender": "未知", "age": "median"})
    df = standardize_codes(df, DEPT_NAME, "dept_code", new_column="dept_name", default="未知科室")
    df = standardize_codes(df, VISIT_TYPE_DICT, "visit_type", new_column="visit_type_code", default="UNKNOWN")
    df["age_group"] = df["age"].map(lambda v: age_group_of(None if pd.isna(v) else int(v)))
    df["visit_ym"] = pd.to_datetime(df["visit_date"], errors="coerce").dt.strftime("%Y-%m")
    return df


def _pipeline_inpatient(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(
        columns={
            "patient_name": "patient_name_masked",
            "id_card": "id_card_masked",
            "phone": "phone_masked",
        }
    )
    df = dedupe(df, ["visit_id"])
    # 日期逻辑校验：出院日期不得早于入院日期
    admit = pd.to_datetime(df["admit_date"], errors="coerce")
    discharge = pd.to_datetime(df["discharge_date"], errors="coerce")
    bad = discharge.notna() & admit.notna() & (discharge < admit)
    if bool(bad.any()):
        print(f"    · 日期逻辑异常剔除 {int(bad.sum())} 行（出院 < 入院）")
        df = df.loc[~bad].reset_index(drop=True)
    df = mask_privacy(df, ["patient_name_masked", "id_card_masked", "phone_masked"])
    df = fill_missing(df, {"gender": "未知", "age": "median", "stay_days": 0})
    df = standardize_codes(df, DEPT_NAME, "dept_code", new_column="dept_name", default="未知科室")
    df = standardize_codes(df, DISEASE_NAME, "disease_code", new_column="disease_name", default="未知病种")
    df = standardize_codes(df, DRG_CODE, "disease_code", new_column="drg_code", default="UNGROUPED")
    df["rw"] = df["disease_code"].map(DRG_RW)
    df["age_group"] = df["age"].map(lambda v: age_group_of(None if pd.isna(v) else int(v)))
    return df


def _pipeline_charge(df: pd.DataFrame) -> pd.DataFrame:
    df = dedupe(df, ["charge_id"])
    df = standardize_codes(df, DEPT_NAME, "dept_code", new_column="dept_name", default="未知科室")
    df = standardize_codes(df, FEE_CLASS, "fee_type_code", new_column="fee_class", default="其他收入")
    df = standardize_codes(df, VISIT_TYPE_DICT, "visit_type", new_column="visit_type_code", default="UNKNOWN")
    df["fee_ym"] = pd.to_datetime(df["fee_date"], errors="coerce").dt.strftime("%Y-%m")
    return df


def _pipeline_emr(df: pd.DataFrame) -> pd.DataFrame:
    df = dedupe(df, ["record_id"])
    df = standardize_codes(df, DEPT_NAME, "dept_code", new_column="dept_name", default="未知科室")
    df = standardize_codes(df, DISEASE_NAME, "disease_code", new_column="disease_name", default="未知病种")
    df = standardize_codes(df, DRG_CODE, "disease_code", new_column="drg_code", default="UNGROUPED")
    return df


def _pipeline_lis(df: pd.DataFrame) -> pd.DataFrame:
    df = dedupe(df, ["report_id"])
    df = standardize_codes(df, LIS_RESULT_FLAG, "result_text", new_column="result_flag", default="未知")
    return df


def _pipeline_finance(df: pd.DataFrame) -> pd.DataFrame:
    df = dedupe(df, ["record_id"])
    df = standardize_codes(df, DEPT_NAME, "dept_code", new_column="dept_name", default="未知科室")
    df["stat_ym"] = pd.to_datetime(df["stat_date"], errors="coerce").dt.strftime("%Y-%m")
    return df


# DWD 表 -> (ODS 来源表, 加工流水线, 业务主键)
PIPELINES: dict[str, tuple[str, Any, tuple[str, ...]]] = {
    "dwd_outpatient_visit_detail": ("ods_his_outpatient_visit", _pipeline_outpatient, ("visit_id",)),
    "dwd_inpatient_visit_detail": ("ods_his_inpatient_visit", _pipeline_inpatient, ("visit_id",)),
    "dwd_charge_detail": ("ods_his_charge_detail", _pipeline_charge, ("charge_id",)),
    "dwd_emr_record_detail": ("ods_emr_record", _pipeline_emr, ("record_id",)),
    "dwd_lis_report_detail": ("ods_lis_report", _pipeline_lis, ("report_id",)),
    "dwd_finance_daily_detail": ("ods_finance_excel", _pipeline_finance, ("record_id",)),
}


# ---------------------------------------------------------------- 步骤 3-3：写入与串跑
def write_dwd(table: str, batch_date: date | str | None = None, *, engine: Engine | None = None) -> int:
    """单表加工：读取 ODS 该批次数据 -> 清洗算子流水线 -> 幂等写入 DWD，返回行数。"""
    if table not in PIPELINES:
        raise KeyError(f"未配置加工流水线的 DWD 表：{table}")
    ods_table, pipeline, _keys = PIPELINES[table]
    bd = normalize_batch_date(batch_date)
    eng = engine or get_engine()

    df = read_table_df(eng, ODS_TABLES[ods_table], bd)
    if df.empty:
        print(f"  [WARN] {ods_table} 批次 {bd} 无数据，跳过 {table}")
        return 0

    print(f"  [加工] {ods_table} ({len(df)} 行) -> {table}")
    cleaned = pipeline(df)
    rows = load_by_batch(eng, DWD_TABLES[table], cleaned, bd)
    print(f"  [OK]   {table} 写入 {rows} 行")
    return rows


def run_clean_all(batch_date: date | str | None = None, *, engine: Engine | None = None) -> dict[str, int]:
    """逐表执行 ODS -> DWD 分层清洗，返回 {DWD 表名: 行数}。"""
    bd = normalize_batch_date(batch_date)
    eng = engine or get_engine()
    result: dict[str, int] = {}
    print(f"[清洗] 批次日期 {bd}，共 {len(PIPELINES)} 张 DWD 表")
    for table in PIPELINES:
        result[table] = write_dwd(table, bd, engine=eng)
    print(f"[清洗] 完成，共写入 {sum(result.values())} 行")
    return result


if __name__ == "__main__":  # 手工自检：python -m etl.jobs.clean_dwd
    from etl.config.settings import DEFAULT_BATCH_DATE

    print("脱敏算子自检：")
    print("  姓名:", mask_name("张秀兰"), "| 身份证:", mask_id_card("11018451848947609"), "| 手机:", mask_phone("13873577907"))
    run_clean_all(DEFAULT_BATCH_DATE)
