"""公共维表初始化与维表读取（阶段三 · 步骤 1、4）。

    init_dim(engine)        全量刷新 6 张维表（先删后插，SCD1 覆盖，幂等）
    verify_dim(engine)      校验维表行数、唯一索引、引用完整性，返回核对明细
    load_dim_map(table)     读取维表为 {编码: 行字典} 映射，供宽表加工关联使用
    dept_map / disease_map / fee_type_map   常用维表快捷读取
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.engine import Engine

from etl.config.dim_schema import DIM_TABLES
from etl.config.dim_seed import (
    DEPARTMENT_ROWS,
    DIM_EXPECTED_ROWS,
    DISEASE_ROWS,
    DRG_ROWS,
    FEE_TYPE_ROWS,
    VISIT_TYPE_ROWS,
    build_date_rows,
)
from etl.config.settings import get_engine


# ---------------------------------------------------------------- 数据组装
def _department_records() -> list[dict[str, Any]]:
    return [
        {
            "dept_code": code,
            "dept_name": name,
            "parent_code": parent,
            "dept_level": level,
            "dept_type": dept_type,
            "org_area": org_area,
            "bed_cnt": bed_cnt,
            "doctor_cnt": doctor_cnt,
            "nurse_cnt": nurse_cnt,
            "is_active": 1,
        }
        for code, name, parent, level, dept_type, org_area, bed_cnt, doctor_cnt, nurse_cnt in DEPARTMENT_ROWS
    ]


def _disease_records() -> list[dict[str, Any]]:
    return [
        {
            "disease_code": code,
            "disease_name": name,
            "disease_category": category,
            "drg_code": drg_code,
            "drg_name": drg_name,
            "rw": rw,
            "dip_group": dip_group,
        }
        for code, name, category, drg_code, drg_name, rw, dip_group in DISEASE_ROWS
    ]


def _drg_records() -> list[dict[str, Any]]:
    return [
        {"drg_code": drg_code, "drg_name": drg_name, "disease_code": disease_code, "rw": rw}
        for disease_code, drg_code, drg_name, rw in DRG_ROWS
    ]


def _fee_type_records() -> list[dict[str, Any]]:
    return [
        {
            "fee_type_code": code,
            "fee_type_name": name,
            "fee_class": fee_class,
            "is_drug": is_drug,
            "is_consumable": is_consumable,
            "sort_no": sort_no,
        }
        for code, name, fee_class, is_drug, is_consumable, sort_no in FEE_TYPE_ROWS
    ]


def _visit_type_records() -> list[dict[str, Any]]:
    return [
        {"visit_type_code": code, "visit_type_name": name, "visit_category": category}
        for code, name, category in VISIT_TYPE_ROWS
    ]


def _date_records() -> list[dict[str, Any]]:
    return build_date_rows()


SEED_BUILDERS = {
    "dim_department": _department_records,
    "dim_date": _date_records,
    "dim_disease": _disease_records,
    "dim_fee_type": _fee_type_records,
    "dim_drg_group": _drg_records,
    "dim_visit_type": _visit_type_records,
}


# ---------------------------------------------------------------- 初始化
def init_dim(engine: Engine | None = None) -> dict[str, int]:
    """全量刷新公共维表，返回 {维表名: 行数}。"""
    eng = engine or get_engine()
    result: dict[str, int] = {}
    print("[维表] 开始初始化公共维表（全量刷新，SCD1 覆盖）")
    for table_name, builder in SEED_BUILDERS.items():
        table = DIM_TABLES[table_name]
        records = builder()
        with eng.begin() as conn:
            conn.execute(delete(table))
            if records:
                conn.execute(table.insert(), records)
        result[table_name] = len(records)
        print(f"  [OK] {table_name:<16} {len(records):>5} 行")
    print(f"[维表] 完成，共 {sum(result.values())} 行（{len(result)} 张维表）")
    return result


# ---------------------------------------------------------------- 校验
def verify_dim(engine: Engine | None = None) -> list[dict[str, Any]]:
    """校验维表行数、唯一索引、引用完整性。"""
    eng = engine or get_engine()
    checks: list[dict[str, Any]] = []

    # 1) 行数核对
    for table_name, expected in DIM_EXPECTED_ROWS.items():
        table = DIM_TABLES[table_name]
        with eng.connect() as conn:
            actual = int(conn.execute(select(func.count()).select_from(table)).scalar_one())
        checks.append(
            {
                "check": "维表行数",
                "table": table_name,
                "expected": expected,
                "actual": actual,
                "ok": actual == expected,
                "detail": f"{actual} 行",
            }
        )

    # 2) 唯一索引（主键重复检查）
    pk_map = {
        "dim_department": "dept_code",
        "dim_date": "date_key",
        "dim_disease": "disease_code",
        "dim_fee_type": "fee_type_code",
        "dim_drg_group": "drg_code",
        "dim_visit_type": "visit_type_code",
    }
    for table_name, pk in pk_map.items():
        table = DIM_TABLES[table_name]
        with eng.connect() as conn:
            total = int(conn.execute(select(func.count()).select_from(table)).scalar_one())
            distinct = int(
                conn.execute(select(func.count(func.distinct(table.c[pk])))).scalar_one()
            )
        checks.append(
            {
                "check": "主键唯一",
                "table": table_name,
                "expected": total,
                "actual": distinct,
                "ok": total == distinct,
                "detail": f"{pk} 唯一值 {distinct}/{total}",
            }
        )

    # 3) 引用完整性：科室上级、病种 DRG 关联
    depts = load_dim_map("dim_department", eng)
    orphan_parent = [c for c, row in depts.items() if row.get("parent_code") and row["parent_code"] not in depts]
    checks.append(
        {
            "check": "科室上级引用",
            "table": "dim_department",
            "expected": 0,
            "actual": len(orphan_parent),
            "ok": not orphan_parent,
            "detail": f"孤立上级 {orphan_parent}" if orphan_parent else "全部上级科室可解析",
        }
    )

    drg_grouped = sum(1 for row in load_dim_map("dim_disease", eng).values() if row.get("drg_code"))
    total_disease = len(DIM_EXPECTED_ROWS) and DIM_EXPECTED_ROWS["dim_disease"]
    checks.append(
        {
            "check": "病种 DRG 分组完整",
            "table": "dim_disease",
            "expected": total_disease,
            "actual": drg_grouped,
            "ok": drg_grouped == total_disease,
            "detail": f"{drg_grouped}/{total_disease} 个病种已映射 DRG 组",
        }
    )

    # 4) 日期维覆盖统计期
    with eng.connect() as conn:
        covered = int(
            conn.execute(
                select(func.count()).select_from(DIM_TABLES["dim_date"]).where(DIM_TABLES["dim_date"].c.in_stat_period == 1)
            ).scalar_one()
        )
    checks.append(
        {
            "check": "日期维覆盖统计期",
            "table": "dim_date",
            "expected": 91,
            "actual": covered,
            "ok": covered == 91,
            "detail": f"统计期内 {covered} 天（应为 91 天）",
        }
    )
    return checks


# ---------------------------------------------------------------- 维表读取
def load_dim_map(table_name: str, engine: Engine | None = None) -> dict[str, dict[str, Any]]:
    """把维表读成 {主键值: 行字典} 映射。"""
    table = DIM_TABLES[table_name]
    pk = list(table.primary_key.columns)[0].name
    eng = engine or get_engine()
    with eng.connect() as conn:
        rows = conn.execute(select(table)).mappings().all()
    return {str(row[pk]): dict(row) for row in rows}


def dept_map(engine: Engine | None = None) -> dict[str, dict[str, Any]]:
    """科室维表映射；level=1 的科室系也包含在内（用于上级编码解析）。"""
    return load_dim_map("dim_department", engine)


def disease_map(engine: Engine | None = None) -> dict[str, dict[str, Any]]:
    return load_dim_map("dim_disease", engine)


def fee_type_map(engine: Engine | None = None) -> dict[str, dict[str, Any]]:
    return load_dim_map("dim_fee_type", engine)


def drg_group_map(engine: Engine | None = None) -> dict[str, dict[str, Any]]:
    return load_dim_map("dim_drg_group", engine)


if __name__ == "__main__":  # 手工自检：python -m etl.jobs.init_dim
    from etl.config.settings import init_ods_dwd_tables

    init_ods_dwd_tables()
    init_dim()
    print("\n维表校验：")
    for row in verify_dim():
        print(f"  [{'OK  ' if row['ok'] else 'FAIL'}] {row['check']:<16} {row['table']:<16} {row['detail']}")
