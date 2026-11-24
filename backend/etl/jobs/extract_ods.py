"""ODS 贴源层采集与幂等装载（阶段二 · 步骤 1、2）。

对外能力（对应《项目开发流程》阶段二任务 T03/T04）：
    extract_his_outpatient(start_date, end_date)   抽取 HIS 门诊就诊
    extract_his_inpatient(start_date, end_date)    抽取 HIS 住院
    extract_his_charge(start_date, end_date)       抽取 HIS 收费明细
    extract_lis(start_date, end_date)              抽取 LIS 检验报告
    extract_emr(start_date, end_date)              抽取 EMR 病历
    extract_finance_excel(path)                    解析财务 Excel/CSV
    extract_hr_staff(start_date, end_date)         抽取人事科室人力台账
    load_to_ods(df, table, batch_date)             按批次日期先删后插（幂等）
    run_extract_all(start_date, end_date)          串跑全部 7 个源并装载
    verify_ods_rows(batch_date)                    核对 ODS 行数与基线

装载约定：每张表额外写入 etl_batch_date / etl_batch_id / etl_load_time，
同一批次日期重跑时先删除该批次旧数据，保证幂等可重复执行。
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from etl.config.loader import build_records as _build_records
from etl.config.loader import load_by_batch
from etl.config.ods_schema import ODS_TABLES
from etl.config.settings import batch_id_of, get_engine, normalize_batch_date
from etl.config.source_config import get_source, resolve_location

# 各源对应的日期过滤字段（增量抽取依据）
SOURCE_DATE_COLUMN: dict[str, str] = {
    "his_outpatient": "visit_date",
    "his_inpatient": "admit_date",
    "his_charge": "fee_date",
    "emr_record": "visit_date",
    "lis_report": "report_date",
    "hr_staff": "stat_date",
}


# ---------------------------------------------------------------- 内部工具
def _read_source_csv(source_name: str, **read_csv_kwargs: Any) -> pd.DataFrame:
    """按数据源注册信息读取 CSV（UTF-8），统一以字符串读入后再由装载体转型。"""
    source = get_source(source_name)
    path = resolve_location(source)
    if not path.exists():
        raise FileNotFoundError(f"源文件不存在：{path}（数据源 {source_name}）")
    # utf-8-sig 兼容带 BOM 的源文件（data/ 下 CSV 均带 BOM）
    kwargs: dict[str, Any] = {"encoding": "utf-8-sig", "dtype": str, "keep_default_na": False}
    kwargs.update(read_csv_kwargs)
    df = pd.read_csv(path, **kwargs)
    df.attrs["source_name"] = source_name
    df.attrs["source_path"] = str(path)
    return df


def _filter_period(df: pd.DataFrame, column: str, start_date: str, end_date: str) -> pd.DataFrame:
    """按业务日期闭区间过滤 [start_date, end_date]。"""
    if column not in df.columns:
        return df
    values = pd.to_datetime(df[column], errors="coerce")
    mask = values.between(pd.Timestamp(start_date), pd.Timestamp(end_date))
    return df.loc[mask].reset_index(drop=True)


def build_records(df: pd.DataFrame, table_name: str, batch_date: date | str | None = None) -> list[dict[str, Any]]:
    """把 DataFrame 规整为 ODS 目标表记录（实现复用 etl.config.loader）。"""
    if table_name not in ODS_TABLES:
        raise KeyError(f"未知 ODS 表：{table_name}，可选 {sorted(ODS_TABLES)}")
    return _build_records(df, ODS_TABLES[table_name], batch_date)


# ---------------------------------------------------------------- 步骤 2-1：各源数据抽取函数
def extract_his_outpatient(start_date: str, end_date: str) -> pd.DataFrame:
    """抽取 HIS 门诊就诊数据（按 visit_date 过滤）。"""
    return _filter_period(_read_source_csv("his_outpatient"), "visit_date", start_date, end_date)


def extract_his_inpatient(start_date: str, end_date: str) -> pd.DataFrame:
    """抽取 HIS 住院数据（按 admit_date 过滤）。"""
    return _filter_period(_read_source_csv("his_inpatient"), "admit_date", start_date, end_date)


def extract_his_charge(start_date: str, end_date: str) -> pd.DataFrame:
    """抽取 HIS 收费明细（按 fee_date 过滤；小时增量时传同一天的起止日期）。"""
    return _filter_period(_read_source_csv("his_charge"), "fee_date", start_date, end_date)


def extract_lis(start_date: str, end_date: str) -> pd.DataFrame:
    """抽取 LIS 检验报告（按 report_date 过滤）。"""
    return _filter_period(_read_source_csv("lis_report"), "report_date", start_date, end_date)


def extract_emr(start_date: str, end_date: str) -> pd.DataFrame:
    """抽取 EMR 病历数据（按 visit_date 过滤）。"""
    return _filter_period(_read_source_csv("emr_record"), "visit_date", start_date, end_date)


def extract_hr_staff(start_date: str, end_date: str) -> pd.DataFrame:
    """抽取人事系统科室人力台账（按 stat_date / 台账月末快照过滤）。"""
    return _filter_period(_read_source_csv("hr_staff"), "stat_date", start_date, end_date)


def extract_finance_excel(path: str | None = None) -> pd.DataFrame:
    """解析财务 Excel/CSV 文件；path 为空时使用数据源注册的文件路径。"""
    if path is None:
        path = str(resolve_location(get_source("finance_excel")))
    if str(path).lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(path, dtype=str)  # 需要 openpyxl
    else:
        df = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    df.attrs["source_path"] = str(path)
    return df


# ---------------------------------------------------------------- 步骤 1-3：幂等装载
def load_to_ods(
    df: pd.DataFrame,
    table: str,
    batch_date: date | str | None = None,
    *,
    engine: Engine | None = None,
) -> int:
    """把 DataFrame 幂等写入 ODS 表，返回写入行数。

    幂等策略：`DELETE FROM <ods_table> WHERE etl_batch_date = :batch_date` 后批量 INSERT。
    """
    if table not in ODS_TABLES:
        raise KeyError(f"未知 ODS 表：{table}，可选 {sorted(ODS_TABLES)}")
    return load_by_batch(engine or get_engine(), ODS_TABLES[table], df, batch_date)


def count_ods_rows(table: str, batch_date: date | str | None = None, engine: Engine | None = None) -> int:
    """统计 ODS 表行数（给定 batch_date 时仅统计该批次）。"""
    tbl = ODS_TABLES[table]
    stmt = select(func.count()).select_from(tbl)
    if batch_date is not None:
        stmt = stmt.where(tbl.c.etl_batch_date == normalize_batch_date(batch_date))
    with (engine or get_engine()).connect() as conn:
        return int(conn.execute(stmt).scalar_one())


# ---------------------------------------------------------------- 步骤 2-2：串跑入口
EXTRACTORS: dict[str, tuple[str, Any]] = {
    "ods_his_outpatient_visit": ("his_outpatient", extract_his_outpatient),
    "ods_his_inpatient_visit": ("his_inpatient", extract_his_inpatient),
    "ods_his_charge_detail": ("his_charge", extract_his_charge),
    "ods_emr_record": ("emr_record", extract_emr),
    "ods_lis_report": ("lis_report", extract_lis),
    "ods_hr_staff": ("hr_staff", extract_hr_staff),
}


def run_extract_all(
    start_date: str,
    end_date: str,
    batch_date: date | str | None = None,
    *,
    engine: Engine | None = None,
    include_finance: bool = True,
) -> dict[str, int]:
    """串跑全部数据源：抽取 -> 装载，返回 {ODS 表名: 写入行数}。"""
    bd = normalize_batch_date(batch_date)
    eng = engine or get_engine()
    result: dict[str, int] = {}

    print(f"[采集] 统计期 {start_date} ~ {end_date}，批次日期 {bd}，批次号 {batch_id_of(bd)}")
    for table, (source_name, extractor) in EXTRACTORS.items():
        df = extractor(start_date, end_date)
        rows = load_to_ods(df, table, bd, engine=eng)
        result[table] = rows
        print(f"  [OK] {source_name:<16} -> {table:<26} {rows:>6} 行")

    if include_finance:
        df = extract_finance_excel()
        rows = load_to_ods(df, "ods_finance_excel", bd, engine=eng)
        result["ods_finance_excel"] = rows
        print(f"  [OK] {'finance_excel':<16} -> {'ods_finance_excel':<26} {rows:>6} 行")

    print(f"[采集] 完成，共写入 {sum(result.values())} 行（{len(result)} 张 ODS 表）")
    return result


def verify_ods_rows(batch_date: date | str | None = None, engine: Engine | None = None) -> list[dict[str, Any]]:
    """核对 ODS 各表行数与基线是否一致，返回核对明细。"""
    from etl.config.baseline import ODS_EXPECTED_ROWS

    rows: list[dict[str, Any]] = []
    for table, expected in ODS_EXPECTED_ROWS.items():
        actual = count_ods_rows(table, batch_date, engine)
        rows.append({"table": table, "expected": expected, "actual": actual, "ok": actual == expected})
    return rows


if __name__ == "__main__":  # 手工自检：python -m etl.jobs.extract_ods
    from etl.config.settings import DEFAULT_BATCH_DATE, STAT_PERIOD_END, STAT_PERIOD_START, init_ods_dwd_tables

    init_ods_dwd_tables()
    run_extract_all(STAT_PERIOD_START, STAT_PERIOD_END, DEFAULT_BATCH_DATE)
    print("\n行数核对：")
    for row in verify_ods_rows(DEFAULT_BATCH_DATE):
        print(f"  [{'OK  ' if row['ok'] else 'FAIL'}] {row['table']:<28} 期望 {row['expected']:>6} / 实际 {row['actual']:>6}")
