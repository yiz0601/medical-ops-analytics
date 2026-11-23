"""通用装载工具：DataFrame -> 记录列表 -> 按批次幂等写入。

ODS 与 DWD 两层装载共用本模块，避免两处重复实现类型转换与幂等删除逻辑。
"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

import pandas as pd
from sqlalchemy import Date as SADate
from sqlalchemy import DateTime as SADateTime
from sqlalchemy import Integer as SAInteger
from sqlalchemy import Numeric as SANumeric
from sqlalchemy import Table, delete
from sqlalchemy.engine import Engine

from etl.config.settings import batch_id_of, normalize_batch_date


def pythonize(value: Any) -> Any:
    """把 numpy/pandas 标量转成 Python 原生类型，缺失值统一为 None。"""
    if value is None or value is pd.NaT or value is pd.NA:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            value = value.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def build_records(df: pd.DataFrame, table: Table, batch_date: date | str | None = None) -> list[dict[str, Any]]:
    """把 DataFrame 规整为目标表记录（按列类型转换 + 追加 ETL 元数据字段）。"""
    bd = normalize_batch_date(batch_date)
    keep = [c.name for c in table.columns if c.name in df.columns]
    frame = df.loc[:, keep].copy()

    for name in keep:
        col_type = table.columns[name].type
        series = frame[name]
        if isinstance(col_type, SADate):
            frame[name] = pd.to_datetime(series, errors="coerce").dt.date
        elif isinstance(col_type, SAInteger):
            frame[name] = pd.to_numeric(series, errors="coerce").round().astype("Int64")
        elif isinstance(col_type, SANumeric):
            frame[name] = pd.to_numeric(series, errors="coerce").round(2)
        elif isinstance(col_type, SADateTime):
            frame[name] = pd.to_datetime(series, errors="coerce")

    frame["etl_batch_date"] = bd
    frame["etl_batch_id"] = batch_id_of(bd)
    frame["etl_load_time"] = datetime.now()

    return [{k: pythonize(v) for k, v in raw.items()} for raw in frame.to_dict("records")]


def load_by_batch(
    engine: Engine,
    table: Table,
    df: pd.DataFrame,
    batch_date: date | str | None = None,
) -> int:
    """按批次日期先删后插（幂等），返回写入行数。"""
    bd = normalize_batch_date(batch_date)
    records = build_records(df, table, bd)
    with engine.begin() as conn:
        deleted = conn.execute(delete(table).where(table.c.etl_batch_date == bd)).rowcount
        if records:
            conn.execute(table.insert(), records)
    if deleted:
        print(f"    · {table.name}: 清理同批次旧数据 {deleted} 行")
    return len(records)


def read_table_df(
    engine: Engine,
    table: Table,
    batch_date: date | str | None = None,
) -> pd.DataFrame:
    """读取整表（给定 batch_date 时只读该批次），返回 DataFrame。"""
    from sqlalchemy import select

    stmt = select(table)
    if batch_date is not None:
        stmt = stmt.where(table.c.etl_batch_date == normalize_batch_date(batch_date))
    with engine.connect() as conn:
        rows = conn.execute(stmt).mappings().all()
    return pd.DataFrame([dict(r) for r in rows])
