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
    FEE_TYPE_NAME,
    LIS_RESULT_FLAG,
    VISIT_TYPE_DICT,
    age_group_of,
)
from etl.config.dwd_schema import DWD_TABLES
from etl.config.loader import load_by_batch, read_table_df
from etl.config.ods_schema import ODS_TABLES
from etl.config.settings import get_engine, normalize_batch_date
from etl.jobs.init_dim import dept_map, disease_map, fee_type_map


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


def _pipeline_charge(df: pd.DataFrame, engine: Engine | None = None) -> pd.DataFrame:
    """收费明细：关联 dim_fee_type 补标准收费类别码、关联 dim_department 补上级科室系。"""
    df = dedupe(df, ["charge_id"])
    eng = engine or get_engine()
    depts = dept_map(eng)
    fee_types = fee_type_map(eng)
    df = standardize_codes(df, DEPT_NAME, "dept_code", new_column="dept_name", default="未知科室")
    df["dept_parent_code"] = df["dept_code"].map(lambda c: depts.get(str(c), {}).get("parent_code"))
    df = standardize_codes(df, FEE_CLASS, "fee_type_code", new_column="fee_class", default="其他收入")
    df["fee_std_code"] = df["fee_type_code"]
    df["fee_std_name"] = df["fee_type_code"].map(
        lambda c: fee_types.get(str(c), {}).get("fee_type_name") or FEE_TYPE_NAME.get(str(c))
    )
    df["is_drug"] = df["fee_type_code"].map(lambda c: int(fee_types.get(str(c), {}).get("is_drug") or 0))
    df["is_consumable"] = df["fee_type_code"].map(
        lambda c: int(fee_types.get(str(c), {}).get("is_consumable") or 0)
    )
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


# ---------------------------------------------------------------- 阶段三：就诊级 / 收费级明细宽表
def _charge_agg(engine: Engine, batch_date) -> pd.DataFrame:
    """按就诊号聚合收费流水（流水口径：药品/耗材/检查检验/医疗服务性）。"""
    charge = read_table_df(engine, DWD_TABLES["dwd_charge_detail"], batch_date)
    cols = [
        "visit_id",
        "charge_amt_total",
        "charge_drug_amt",
        "charge_consumable_amt",
        "charge_exam_lab_amt",
        "charge_service_amt",
    ]
    if charge.empty:
        return pd.DataFrame(columns=cols)
    amount = pd.to_numeric(charge["amount"], errors="coerce").fillna(0.0)
    frame = pd.DataFrame(
        {
            "visit_id": charge["visit_id"].astype(str),
            "_drug": amount.where(charge["fee_class"] == "药品收入", 0.0),
            "_consumable": amount.where(charge["fee_class"] == "耗材收入", 0.0),
            "_exam_lab": amount.where(charge["fee_class"] == "检查检验收入", 0.0),
            "_service": amount.where(charge["fee_class"] == "医疗服务性收入", 0.0),
            "_total": amount,
        }
    )
    return frame.groupby("visit_id", as_index=False).agg(
        charge_amt_total=("_total", "sum"),
        charge_drug_amt=("_drug", "sum"),
        charge_consumable_amt=("_consumable", "sum"),
        charge_exam_lab_amt=("_exam_lab", "sum"),
        charge_service_amt=("_service", "sum"),
    )


def _attach_dim(wide: pd.DataFrame, depts: dict, diseases: dict) -> tuple[pd.DataFrame, dict[str, int]]:
    """关联科室维表与病种维表，返回宽表与关联未命中统计。"""
    wide["dept_name"] = wide["dept_code"].map(lambda c: depts.get(str(c), {}).get("dept_name"))
    wide["dept_parent_code"] = wide["dept_code"].map(lambda c: depts.get(str(c), {}).get("parent_code"))
    wide["org_area"] = wide["dept_code"].map(lambda c: depts.get(str(c), {}).get("org_area"))
    wide["disease_name"] = wide["disease_code"].map(lambda c: diseases.get(str(c), {}).get("disease_name"))
    wide["drg_code"] = wide["disease_code"].map(lambda c: diseases.get(str(c), {}).get("drg_code"))
    wide["rw"] = wide["disease_code"].map(lambda c: diseases.get(str(c), {}).get("rw"))

    stats = {
        "dept_miss": int(wide["dept_name"].isna().sum()),
        "disease_miss": int(wide["disease_code"].notna().sum() - wide["disease_name"].notna().sum()),
    }
    wide["dept_name"] = wide["dept_name"].fillna("未知科室")
    wide["dept_parent_code"] = wide["dept_parent_code"].fillna("UNKNOWN")
    wide["org_area"] = wide["org_area"].fillna("本部")
    wide["disease_name"] = wide["disease_name"].fillna("无诊断")
    wide["drg_code"] = wide["drg_code"].fillna("UNGROUPED")
    return wide, stats


def _ratio(frame: pd.DataFrame) -> pd.DataFrame:
    """计算药品/耗材占流水比（分母为 0 时记 NULL）。"""
    total = pd.to_numeric(frame["charge_amt_total"], errors="coerce")
    for src, dst in (("charge_drug_amt", "drug_ratio"), ("charge_consumable_amt", "consumable_ratio")):
        num = pd.to_numeric(frame[src], errors="coerce")
        frame[dst] = num.divide(total.where(total > 0))
    return frame


def build_dwd_visit(
    start_date: str | None = None,
    end_date: str | None = None,
    batch_date: date | str | None = None,
    *,
    engine: Engine | None = None,
) -> int:
    """构建就诊级明细宽表 `dwd_visit_detail`（门诊 + 住院统一，含住院天数与费用分项派生列）。"""
    bd = normalize_batch_date(batch_date)
    eng = engine or get_engine()
    depts = dept_map(eng)
    diseases = disease_map(eng)

    op = read_table_df(eng, ODS_TABLES["ods_his_outpatient_visit"], bd)
    ip = read_table_df(eng, ODS_TABLES["ods_his_inpatient_visit"], bd)
    agg = _charge_agg(eng, bd)

    frames: list[pd.DataFrame] = []
    if not op.empty:
        frames.append(
            pd.DataFrame(
                {
                    "visit_id": op["visit_id"].astype(str),
                    "visit_type": "门诊",
                    "visit_type_code": "OPD",
                    "patient_id": op["patient_id"],
                    "patient_name_masked": op["patient_name"].map(mask_name),
                    "gender": op["gender"],
                    "age": op["age"],
                    "dept_code": op["dept_code"],
                    "visit_date": pd.to_datetime(op["visit_date"], errors="coerce").dt.date,
                    "discharge_date": None,
                    "stay_days": None,
                    "bed_no": None,
                    "disease_code": None,
                    "total_fee": op["fee_amount"],
                    "drug_fee": None,
                    "consumable_fee": None,
                }
            )
        )
    if not ip.empty:
        frames.append(
            pd.DataFrame(
                {
                    "visit_id": ip["visit_id"].astype(str),
                    "visit_type": "住院",
                    "visit_type_code": "IPD",
                    "patient_id": ip["patient_id"],
                    "patient_name_masked": ip["patient_name"].map(mask_name),
                    "gender": ip["gender"],
                    "age": ip["age"],
                    "dept_code": ip["dept_code"],
                    "visit_date": pd.to_datetime(ip["admit_date"], errors="coerce").dt.date,
                    "discharge_date": pd.to_datetime(ip["discharge_date"], errors="coerce").dt.date,
                    "stay_days": ip["stay_days"],
                    "bed_no": ip["bed_no"],
                    "disease_code": ip["disease_code"],
                    "total_fee": ip["total_fee"],
                    "drug_fee": ip["drug_fee"],
                    "consumable_fee": ip["consumable_fee"],
                }
            )
        )

    if not frames:
        print("  [WARN] 无门诊/住院数据，跳过 dwd_visit_detail")
        return 0

    wide = pd.concat(frames, ignore_index=True)
    if start_date and end_date:
        visit_dates = pd.to_datetime(wide["visit_date"], errors="coerce")
        wide = wide.loc[visit_dates.between(pd.Timestamp(start_date), pd.Timestamp(end_date))].reset_index(drop=True)
    wide = dedupe(wide, ["visit_id"])
    wide["visit_ym"] = pd.to_datetime(wide["visit_date"], errors="coerce").dt.strftime("%Y-%m")
    wide["age_group"] = wide["age"].map(lambda v: age_group_of(None if pd.isna(v) else int(v)))

    wide, stats = _attach_dim(wide, depts, diseases)
    wide = wide.merge(agg, on="visit_id", how="left")
    for col in (
        "charge_amt_total",
        "charge_drug_amt",
        "charge_consumable_amt",
        "charge_exam_lab_amt",
        "charge_service_amt",
    ):
        wide[col] = pd.to_numeric(wide[col], errors="coerce").fillna(0.0)
    wide = _ratio(wide)

    total = len(wide)
    dept_hit = 100.0 * (total - stats["dept_miss"]) / total if total else 0.0
    disease_total = int(wide["disease_code"].notna().sum())
    disease_hit = 100.0 * (disease_total - stats["disease_miss"]) / disease_total if disease_total else 100.0
    rows = load_by_batch(eng, DWD_TABLES["dwd_visit_detail"], wide, bd)
    print(
        f"  [OK]   dwd_visit_detail 写入 {rows} 行"
        f"（门诊 {(wide['visit_type'] == '门诊').sum()} / 住院 {(wide['visit_type'] == '住院').sum()}，"
        f"科室命中率 {dept_hit:.2f}%，病种命中率 {disease_hit:.2f}%）"
    )
    return rows


def build_dwd_charge(
    start_date: str | None = None,
    end_date: str | None = None,
    batch_date: date | str | None = None,
    *,
    engine: Engine | None = None,
) -> int:
    """构建收费级明细宽表 `dwd_charge_detail`（关联科室与标准收费类别码）。"""
    bd = normalize_batch_date(batch_date)
    eng = engine or get_engine()
    df = read_table_df(eng, ODS_TABLES["ods_his_charge_detail"], bd)
    if df.empty:
        print("  [WARN] 无收费数据，跳过 dwd_charge_detail")
        return 0
    cleaned = _pipeline_charge(df, eng)
    if start_date and end_date:
        fee_dates = pd.to_datetime(cleaned["fee_date"], errors="coerce")
        cleaned = cleaned.loc[fee_dates.between(pd.Timestamp(start_date), pd.Timestamp(end_date))].reset_index(drop=True)
    rows = load_by_batch(eng, DWD_TABLES["dwd_charge_detail"], cleaned, bd)
    std_hit = 100.0 * cleaned["fee_std_name"].notna().mean() if len(cleaned) else 0.0
    print(f"  [OK]   dwd_charge_detail 写入 {rows} 行（标准收费类别命中率 {std_hit:.2f}%）")
    return rows


def run_wide_tables(
    start_date: str | None = None,
    end_date: str | None = None,
    batch_date: date | str | None = None,
    *,
    engine: Engine | None = None,
) -> dict[str, int]:
    """构建两张 DWD 明细宽表（收费宽表 -> 就诊宽表，后者依赖前者聚合）。"""
    bd = normalize_batch_date(batch_date)
    eng = engine or get_engine()
    print(f"[宽表] 批次日期 {bd}，构建 DWD 明细宽表")
    return {
        "dwd_charge_detail": build_dwd_charge(start_date, end_date, bd, engine=eng),
        "dwd_visit_detail": build_dwd_visit(start_date, end_date, bd, engine=eng),
    }


# ---------------------------------------------------------------- 阶段三 · 步骤 4：结构与对账校验
def verify_dim_dwd(batch_date: date | str | None = None, *, engine: Engine | None = None) -> list[dict[str, Any]]:
    """校验维表行数、DWD 宽表主键唯一性、DWD 与 ODS 行数对账、维表关联命中率。"""
    from sqlalchemy import func, select

    from etl.config.dim_schema import DIM_TABLES
    from etl.config.dim_seed import DIM_EXPECTED_ROWS

    bd = normalize_batch_date(batch_date)
    eng = engine or get_engine()
    checks: list[dict[str, Any]] = []

    def _count(table, with_batch: bool = True) -> int:
        stmt = select(func.count()).select_from(table)
        if with_batch:
            stmt = stmt.where(table.c.etl_batch_date == bd)
        with eng.connect() as conn:
            return int(conn.execute(stmt).scalar_one())

    # 1) 4 张核心维表行数
    for table_name in ("dim_department", "dim_date", "dim_disease", "dim_fee_type"):
        table = DIM_TABLES[table_name]
        actual = _count(table, with_batch=False)
        expected = DIM_EXPECTED_ROWS[table_name]
        checks.append(
            {
                "check": "核心维表行数>0",
                "table": table_name,
                "expected": expected,
                "actual": actual,
                "ok": actual == expected and actual > 0,
                "detail": f"{actual} 行（期望 {expected}）",
            }
        )

    # 2) DWD 宽表主键唯一
    for table_name, pk in (("dwd_visit_detail", "visit_id"), ("dwd_charge_detail", "charge_id")):
        table = DWD_TABLES[table_name]
        total = _count(table)
        with eng.connect() as conn:
            distinct = int(conn.execute(select(func.count(func.distinct(table.c[pk])))).scalar_one())
        checks.append(
            {
                "check": "DWD 宽表主键唯一",
                "table": table_name,
                "expected": total,
                "actual": distinct,
                "ok": total == distinct,
                "detail": f"{pk} 唯一值 {distinct}/{total}",
            }
        )

    # 3) 与 ODS 行数对账
    op_rows = _count(ODS_TABLES["ods_his_outpatient_visit"])
    ip_rows = _count(ODS_TABLES["ods_his_inpatient_visit"])
    visit_rows = _count(DWD_TABLES["dwd_visit_detail"])
    checks.append(
        {
            "check": "就诊宽表与ODS对账",
            "table": "dwd_visit_detail",
            "expected": op_rows + ip_rows,
            "actual": visit_rows,
            "ok": visit_rows == op_rows + ip_rows,
            "detail": f"门诊 {op_rows} + 住院 {ip_rows} = {op_rows + ip_rows}，宽表 {visit_rows}",
        }
    )
    charge_ods = _count(ODS_TABLES["ods_his_charge_detail"])
    charge_dwd = _count(DWD_TABLES["dwd_charge_detail"])
    checks.append(
        {
            "check": "收费宽表与ODS对账",
            "table": "dwd_charge_detail",
            "expected": charge_ods,
            "actual": charge_dwd,
            "ok": charge_ods == charge_dwd,
            "detail": f"ODS {charge_ods} 行 / DWD {charge_dwd} 行",
        }
    )

    # 4) 维表关联命中率
    frame = read_table_df(eng, DWD_TABLES["dwd_visit_detail"], bd)
    if not frame.empty:
        dept_miss = int((frame["dept_name"] == "未知科室").sum())
        ip_mask = frame["visit_type"] == "住院"
        drg_miss = int(ip_mask.sum() - int((frame.loc[ip_mask, "drg_code"] != "UNGROUPED").sum()))
        checks.append(
            {
                "check": "科室维表命中率100%",
                "table": "dwd_visit_detail",
                "expected": 0,
                "actual": dept_miss,
                "ok": dept_miss == 0,
                "detail": f"未命中 {dept_miss} 行",
            }
        )
        checks.append(
            {
                "check": "病种维表命中率100%",
                "table": "dwd_visit_detail",
                "expected": 0,
                "actual": drg_miss,
                "ok": drg_miss == 0,
                "detail": f"住院病例未分组 {drg_miss} 行",
            }
        )
    return checks


if __name__ == "__main__":  # 手工自检：python -m etl.jobs.clean_dwd
    from etl.config.settings import DEFAULT_BATCH_DATE

    print("脱敏算子自检：")
    print("  姓名:", mask_name("张秀兰"), "| 身份证:", mask_id_card("11018451848947609"), "| 手机:", mask_phone("13873577907"))
    run_clean_all(DEFAULT_BATCH_DATE)
    run_wide_tables(batch_date=DEFAULT_BATCH_DATE)
    print("\n结构与对账校验：")
    for item in verify_dim_dwd(DEFAULT_BATCH_DATE):
        print(f"  [{'OK  ' if item['ok'] else 'FAIL'}] {item['check']:<20} {item['table']:<24} {item['detail']}")
