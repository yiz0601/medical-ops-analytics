"""从 Python 表结构导出 MySQL DDL 与初始化数据（阶段三 · 步骤 1）。

单一事实来源：`etl/config/{dim,ods,dwd,mart}_schema.py` 定义列，`dim_seed.py` 定义维表数据。
本脚本把它们渲染为 `sql/` 下的 MySQL 8.0 建表脚本，保证「代码结构 = 数据库结构」。

    python -m etl.jobs.export_ddl            # 生成全部五层脚本
    python -m etl.jobs.export_ddl --layer dim  # 仅生成维表

生成物：
    sql/dim/dim_tables.sql    维表 DDL + 初始化数据（含 dim_date 递归生成）
    sql/ods/ods_tables.sql    ODS 贴源层 DDL
    sql/dwd/dwd_tables.sql    DWD 明细层 DDL
    sql/dws/dws_tables.sql    DWS 汇总层 DDL
    sql/ads/ads_tables.sql    ADS 集市层 DDL
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import Table
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from etl.config.dim_schema import DIM_TABLES
from etl.config.dim_seed import (
    DATE_END,
    DATE_START,
    DEPARTMENT_ROWS,
    DISEASE_ROWS,
    DRG_ROWS,
    FEE_TYPE_ROWS,
    HOLIDAYS,
    STAT_PERIOD_RANGE,
    VISIT_TYPE_ROWS,
)
from etl.config.dwd_schema import DWD_TABLES
from etl.config.mart_schema import THEME_TABLES, ads_indicator_result, dws_dept_daily
from etl.config.ods_schema import ODS_TABLES
from etl.config.settings import PROJECT_ROOT

SQL_DIR = PROJECT_ROOT / "sql"
HEADER = """-- =============================================================================
-- 医疗运营数据主题分析平台 —— {title}
-- 本文件由 backend/etl/jobs/export_ddl.py 自动生成，请勿手工编辑。
-- 来源：backend/etl/config/{source}
-- 数据库：MySQL 8.0    字符集：utf8mb4    引擎：InnoDB
-- 执行：mysql -h127.0.0.1 -uroot -p < {relpath}
-- =============================================================================

CREATE DATABASE IF NOT EXISTS medical_ops
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_general_ci;

USE medical_ops;
"""


# ---------------------------------------------------------------- 工具
def _literal(value: Any) -> str:
    """把 Python 值渲染为 SQL 字面量。"""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (date, datetime)):
        return f"'{value:%Y-%m-%d}'" if isinstance(value, date) and not isinstance(value, datetime) else f"'{value:%Y-%m-%d %H:%M:%S}'"
    text = str(value).replace("\\", "\\\\").replace("'", "''")
    return f"'{text}'"


_COLUMN_COMMENT_RE = re.compile(
    r"^(?P<indent>\t)(?P<body>.*?) COMMENT (?P<comment>'(?:[^']|'')*')(?P<tail>.*?)(?P<comma>,?)$"
)


def _reorder_comment(ddl: str) -> str:
    """MySQL 要求 COMMENT 位于 DEFAULT / NOT NULL 之后，SQLAlchemy 默认渲染在其前面，这里统一重排。"""
    fixed: list[str] = []
    for raw_line in ddl.splitlines():
        line = raw_line.rstrip()  # SQLAlchemy 会在逗号后留空格，先清理避免误判
        match = _COLUMN_COMMENT_RE.match(line)
        if match:
            body = match.group("body").rstrip()
            tail = match.group("tail").strip()
            comment = match.group("comment")
            rebuilt = f"{match.group('indent')}{body}"
            if tail:
                rebuilt += f" {tail}"
            rebuilt += f" COMMENT {comment}{match.group('comma')}"
            fixed.append(rebuilt)
        else:
            fixed.append(line)
    return "\n".join(fixed)


def _create_table_sql(table: Table, comment: str | None = None) -> str:
    """渲染单表 MySQL DDL（含 IF NOT EXISTS、引擎与字符集）。"""
    ddl = str(CreateTable(table, if_not_exists=True).compile(dialect=mysql.dialect())).strip()
    ddl = _reorder_comment(ddl)
    if ddl.endswith(")"):
        ddl += " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
        if comment:
            ddl += f" COMMENT={_literal(comment)}"
        ddl += ";"
    return ddl


def _insert_sql(table_name: str, columns: list[str], rows: Iterable[dict[str, Any]]) -> str:
    """批量生成 INSERT 语句。"""
    rows = list(rows)
    if not rows:
        return f"-- {table_name}：无初始化数据\n"
    values = ",\n  ".join(
        "(" + ", ".join(_literal(row.get(col)) for col in columns) + ")" for row in rows
    )
    return (
        f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES\n  {values}\n"
        f"ON DUPLICATE KEY UPDATE {', '.join(f'{c}=VALUES({c})' for c in columns[1:])};\n"
    )


def _row_counts_sql(pairs: list[tuple[str, int]]) -> str:
    """生成行数核对 SQL 片段。"""
    body = "\n  UNION ALL ".join(
        f"SELECT '{table}' AS table_name, COUNT(*) AS actual_rows, {expected} AS expected_rows FROM {table}"
        for table, expected in pairs
    )
    return (
        "-- ---------------------------------------------------------------- 行数核对\n"
        "SELECT t.table_name, t.actual_rows, t.expected_rows,\n"
        "       IF(t.actual_rows = t.expected_rows, 'OK', 'FAIL') AS result\nFROM (\n  "
        + body
        + "\n) t;\n"
    )


# ---------------------------------------------------------------- 各层渲染
def render_dim() -> str:
    """维表：DDL + 初始化数据（含日期维递归生成与节假日标记）。"""
    parts = [HEADER.format(title="公共维表建表与初始化脚本（阶段三 · 步骤 1）",
                           source="dim_schema.py + dim_seed.py",
                           relpath="sql/dim/dim_tables.sql")]
    comments = {
        "dim_department": "科室维表（标准码、名称、层级、院区、床位与人力）",
        "dim_date": "日期维表（年/季/月/周/星期/周末/节假日）",
        "dim_disease": "病种维表（ICD 编码、疾病大类、DRG/DIP 分组与权重）",
        "dim_fee_type": "收费类别维表（挂号/检查/检验/治疗/手术/床位/护理/药品/耗材）",
        "dim_drg_group": "DRG 分组维表（扩展：病种 → 组别 → 权重）",
        "dim_visit_type": "号别字典（扩展：普通/专家/急诊/门诊/住院）",
    }
    for name, table in DIM_TABLES.items():
        parts.append(f"\n-- ---------------------------------------------------------------- {name}\n")
        parts.append(_create_table_sql(table, comments.get(name)) + "\n")

    parts.append("\n-- ================================ 初始化数据 ================================\n")

    # 科室
    parts.append("\n-- 科室维表：4 个科室系 + 10 个临床科室（开放床位合计 177）\n")
    parts.append(
        _insert_sql(
            "dim_department",
            ["dept_code", "dept_name", "parent_code", "dept_level", "dept_type", "org_area",
             "bed_cnt", "doctor_cnt", "nurse_cnt", "is_active"],
            [
                {
                    "dept_code": code, "dept_name": name, "parent_code": parent, "dept_level": level,
                    "dept_type": dept_type, "org_area": org_area, "bed_cnt": bed_cnt,
                    "doctor_cnt": doctor_cnt, "nurse_cnt": nurse_cnt, "is_active": 1,
                }
                for code, name, parent, level, dept_type, org_area, bed_cnt, doctor_cnt, nurse_cnt in DEPARTMENT_ROWS
            ],
        )
    )

    # 病种 / DRG / 收费类别 / 号别
    parts.append("\n-- 病种维表：10 个 ICD-10 主诊断（含模拟 DRG 分组与权重）\n")
    parts.append(
        _insert_sql(
            "dim_disease",
            ["disease_code", "disease_name", "disease_category", "drg_code", "drg_name", "rw", "dip_group"],
            [
                {
                    "disease_code": c, "disease_name": n, "disease_category": cat,
                    "drg_code": dg, "drg_name": dn, "rw": rw, "dip_group": dip,
                }
                for c, n, cat, dg, dn, rw, dip in DISEASE_ROWS
            ],
        )
    )
    parts.append("\n-- DRG 分组维表（扩展）\n")
    parts.append(
        _insert_sql(
            "dim_drg_group",
            ["drg_code", "drg_name", "disease_code", "rw"],
            [{"drg_code": dg, "drg_name": dn, "disease_code": dc, "rw": rw} for dc, dg, dn, rw in DRG_ROWS],
        )
    )
    parts.append("\n-- 收费类别维表：10 类（含收入归类与药品/耗材标记）\n")
    parts.append(
        _insert_sql(
            "dim_fee_type",
            ["fee_type_code", "fee_type_name", "fee_class", "is_drug", "is_consumable", "sort_no"],
            [
                {
                    "fee_type_code": c, "fee_type_name": n, "fee_class": fc,
                    "is_drug": d, "is_consumable": m, "sort_no": s,
                }
                for c, n, fc, d, m, s in FEE_TYPE_ROWS
            ],
        )
    )
    parts.append("\n-- 号别字典（扩展）\n")
    parts.append(
        _insert_sql(
            "dim_visit_type",
            ["visit_type_code", "visit_type_name", "visit_category"],
            [{"visit_type_code": c, "visit_type_name": n, "visit_category": cat} for c, n, cat in VISIT_TYPE_ROWS],
        )
    )

    # 日期维：递归生成，覆盖统计期前后各 1 年
    parts.append(
        f"""
-- 日期维表：{DATE_START} ~ {DATE_END}（覆盖数据期 {STAT_PERIOD_RANGE[0]} ~ {STAT_PERIOD_RANGE[1]} 前后各 1 年）
SET SESSION cte_max_recursion_depth = 2000;

INSERT INTO dim_date (date_key, date_value, year, quarter, month, year_month, day_of_month,
                      week_of_year, iso_year, day_of_week, weekday_name, is_weekend,
                      is_holiday, holiday_name, in_stat_period)
WITH RECURSIVE d AS (
  SELECT DATE('{DATE_START}') AS dt
  UNION ALL
  SELECT DATE_ADD(dt, INTERVAL 1 DAY) FROM d WHERE dt < DATE('{DATE_END}')
)
SELECT CAST(DATE_FORMAT(dt, '%Y%m%d') AS UNSIGNED), dt, YEAR(dt), QUARTER(dt), MONTH(dt),
       DATE_FORMAT(dt, '%Y-%m'), DAY(dt), WEEK(dt, 3), YEARWEEK(dt, 3) DIV 100,
       WEEKDAY(dt) + 1,
       ELT(WEEKDAY(dt) + 1, '周一', '周二', '周三', '周四', '周五', '周六', '周日'),
       IF(WEEKDAY(dt) >= 5, 1, 0), 0, '',
       IF(dt BETWEEN '{STAT_PERIOD_RANGE[0]}' AND '{STAT_PERIOD_RANGE[1]}', 1, 0)
FROM d
ON DUPLICATE KEY UPDATE date_value = VALUES(date_value);
"""
    )

    # 节假日标记
    parts.append("\n-- 法定节假日标记（与 backend/etl/config/dim_seed.py 中的 HOLIDAYS 一致）\n")
    holiday_rows = " UNION ALL\n  ".join(
        f"SELECT DATE('{day}') AS dt, {_literal(name)} AS nm" for day, name in sorted(HOLIDAYS.items())
    )
    parts.append(
        "UPDATE dim_date dd\n"
        "JOIN (\n  " + holiday_rows + "\n) h ON h.dt = dd.date_value\n"
        "SET dd.is_holiday = 1, dd.holiday_name = h.nm;\n"
    )

    parts.append("\n-- ---------------------------------------------------------------- 维表校验\n")
    parts.append(
        _row_counts_sql(
            [
                ("dim_department", len(DEPARTMENT_ROWS)),
                ("dim_disease", len(DISEASE_ROWS)),
                ("dim_fee_type", len(FEE_TYPE_ROWS)),
                ("dim_drg_group", len(DRG_ROWS)),
                ("dim_visit_type", len(VISIT_TYPE_ROWS)),
                ("dim_date", (date.fromisoformat(DATE_END) - date.fromisoformat(DATE_START)).days + 1),
            ]
        )
    )
    parts.append(
        "\n-- 统计期天数（应 91）与开放床位合计（应 177）\n"
        "SELECT COUNT(*) AS stat_days FROM dim_date WHERE in_stat_period = 1;\n"
        "SELECT SUM(bed_cnt) AS total_beds FROM dim_department WHERE dept_level = 2;\n"
    )
    return "".join(parts)


def render_layer(layer: str) -> str:
    """渲染 ODS / DWD / DWS / ADS 层的建表脚本。"""
    if layer == "ods":
        tables = ODS_TABLES
        title = "ODS 贴源层建表脚本（阶段二 · 步骤 1）"
        source = "ods_schema.py"
        note = (
            "\n-- 说明：字段与 data/ 下 6 个源 CSV 一一对应，仅追加 3 个 ETL 元数据字段：\n"
            "--       etl_batch_date（批次业务日期，幂等删除键）、etl_batch_id（批次标识）、etl_load_time（入库时间）\n"
        )
    elif layer == "dwd":
        tables = DWD_TABLES
        title = "DWD 明细层建表脚本（阶段二/三 · 步骤 3）"
        source = "dwd_schema.py"
        note = (
            "\n-- 说明：ODS 经去重、填充、编码标准化、隐私脱敏后写入本层；\n"
            "--       dwd_visit_detail 为门诊+住院统一就诊宽表，dwd_charge_detail 为收费宽表（关联科室与标准收费类别码）\n"
        )
    elif layer == "dws":
        tables = {"dws_dept_daily": dws_dept_daily}
        title = "DWS 汇总层建表脚本（阶段三 · DWS 步骤 1）"
        source = "mart_schema.py"
        note = "\n-- 说明：主键（科室码 + 日期）唯一，度量字段覆盖门诊/住院/收入/检验/手术/财务口径\n"
    elif layer == "ads":
        tables = {f"ads_{k}_theme": v for k, v in THEME_TABLES.items()}
        tables["ads_indicator_result"] = ads_indicator_result
        title = "ADS 集市层建表脚本（阶段三 · 集市步骤 2）"
        source = "mart_schema.py"
        note = (
            "\n-- 说明：8 个主题集市表（主键唯一：科室码 + 日期）+ 指标结果表\n"
            "--       ads_indicator_result 唯一键 = 指标编码 + 维度值 + 粒度 + 统计日期\n"
        )
    else:
        raise ValueError(f"未知层级：{layer}")

    relpath = f"sql/{layer}/{layer}_tables.sql"
    parts = [HEADER.format(title=title, source=source, relpath=relpath), note]
    for name, table in tables.items():
        parts.append(f"\n-- ---------------------------------------------------------------- {name}\n")
        parts.append(_create_table_sql(table) + "\n")
    return "".join(parts)


LAYER_RENDERERS = {
    "dim": render_dim,
    "ods": lambda: render_layer("ods"),
    "dwd": lambda: render_layer("dwd"),
    "dws": lambda: render_layer("dws"),
    "ads": lambda: render_layer("ads"),
}


def export(layers: Iterable[str] | None = None) -> dict[str, Path]:
    """生成指定层级的 SQL 脚本，返回 {层: 文件路径}。"""
    targets = list(layers) if layers else list(LAYER_RENDERERS)
    written: dict[str, Path] = {}
    for layer in targets:
        if layer not in LAYER_RENDERERS:
            raise ValueError(f"未知层级：{layer}，可选 {list(LAYER_RENDERERS)}")
        content = LAYER_RENDERERS[layer]()
        target_dir = SQL_DIR / layer
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"{layer}_tables.sql"
        path.write_text(content, encoding="utf-8")
        written[layer] = path
        print(f"  [OK] {path.relative_to(PROJECT_ROOT)}  {len(content.splitlines())} 行")
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="etl.jobs.export_ddl", description="导出 MySQL DDL 与维表初始化数据")
    parser.add_argument("--layer", action="append", choices=list(LAYER_RENDERERS), help="仅导出指定层（可多次）")
    args = parser.parse_args(argv)
    print(f"[DDL] 生成目录：{SQL_DIR}")
    export(args.layer)
    print("[DDL] 完成。执行：mysql -h127.0.0.1 -uroot -p < sql/dim/dim_tables.sql  （依次 dim/ods/dwd/dws/ads）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
