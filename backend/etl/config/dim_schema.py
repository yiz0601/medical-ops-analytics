"""公共维表结构（阶段三 · 步骤 1：4 张核心维表 + 2 张扩展维表）。

MySQL DDL 见 `sql/dim/dim_tables.sql`（列与本文件一致）；初始化数据见 `dim_seed.py`。
"""

from __future__ import annotations

from sqlalchemy import Column, Date, Integer, MetaData, Numeric, String, Table

DIM_METADATA = MetaData()


# ---------------------------------------------------------------- 科室维表
dim_department = Table(
    "dim_department",
    DIM_METADATA,
    Column("dept_code", String(16), primary_key=True, comment="科室标准码"),
    Column("dept_name", String(64), nullable=False, comment="科室名称"),
    Column("parent_code", String(16), comment="上级科室系编码"),
    Column("dept_level", Integer, nullable=False, server_default="2", comment="层级：1 科室系 / 2 临床科室"),
    Column("dept_type", String(32), comment="科室类型"),
    Column("org_area", String(32), comment="院区（数据权限隔离维度）"),
    Column("bed_cnt", Integer, server_default="0", comment="开放床位数"),
    Column("doctor_cnt", Integer, server_default="0", comment="医师数"),
    Column("nurse_cnt", Integer, server_default="0", comment="护士数"),
    Column("is_active", Integer, server_default="1", comment="是否启用"),
)

# ---------------------------------------------------------------- 日期维表
dim_date = Table(
    "dim_date",
    DIM_METADATA,
    Column("date_key", Integer, primary_key=True, autoincrement=False, comment="日期键 YYYYMMDD"),
    Column("date_value", Date, nullable=False, comment="日期值"),
    Column("year", Integer, nullable=False, comment="年"),
    Column("quarter", Integer, comment="季度"),
    Column("month", Integer, comment="月"),
    Column("year_month", String(7), comment="年月 YYYY-MM"),
    Column("day_of_month", Integer, comment="日"),
    Column("week_of_year", Integer, comment="年内第几周（ISO）"),
    Column("iso_year", Integer, comment="ISO 年"),
    Column("day_of_week", Integer, comment="星期（1=周一）"),
    Column("weekday_name", String(8), comment="星期名称"),
    Column("is_weekend", Integer, comment="是否周末"),
    Column("is_holiday", Integer, comment="是否法定节假日"),
    Column("holiday_name", String(32), comment="节假日名称"),
    Column("in_stat_period", Integer, comment="是否在数据统计期内"),
)

# ---------------------------------------------------------------- 病种维表
dim_disease = Table(
    "dim_disease",
    DIM_METADATA,
    Column("disease_code", String(16), primary_key=True, comment="ICD-10 编码"),
    Column("disease_name", String(64), nullable=False, comment="病种名称"),
    Column("disease_category", String(32), comment="疾病大类"),
    Column("drg_code", String(16), comment="DRG 组编码（模拟分组）"),
    Column("drg_name", String(64), comment="DRG 组名称"),
    Column("rw", Numeric(6, 2), comment="DRG 权重 RW"),
    Column("dip_group", String(32), comment="DIP 病种分值组"),
)

# ---------------------------------------------------------------- 收费类别维表
dim_fee_type = Table(
    "dim_fee_type",
    DIM_METADATA,
    Column("fee_type_code", String(16), primary_key=True, comment="收费类别编码"),
    Column("fee_type_name", String(32), nullable=False, comment="收费类别名称"),
    Column("fee_class", String(32), comment="收入归类：药品/耗材/检查检验/医疗服务性"),
    Column("is_drug", Integer, server_default="0", comment="是否药品"),
    Column("is_consumable", Integer, server_default="0", comment="是否耗材"),
    Column("sort_no", Integer, server_default="0", comment="排序号"),
)

# ---------------------------------------------------------------- DRG 分组维表（扩展）
dim_drg_group = Table(
    "dim_drg_group",
    DIM_METADATA,
    Column("drg_code", String(16), primary_key=True, comment="DRG 组编码"),
    Column("drg_name", String(64), comment="DRG 组名称"),
    Column("disease_code", String(16), comment="对应 ICD-10 主诊断"),
    Column("rw", Numeric(6, 2), comment="权重 RW"),
)

# ---------------------------------------------------------------- 号别字典（扩展）
dim_visit_type = Table(
    "dim_visit_type",
    DIM_METADATA,
    Column("visit_type_code", String(8), primary_key=True, comment="号别编码"),
    Column("visit_type_name", String(16), nullable=False, comment="号别名称"),
    Column("visit_category", String(16), comment="归类：门诊/门急诊/住院"),
)

DIM_TABLES: dict[str, Table] = {
    "dim_department": dim_department,
    "dim_date": dim_date,
    "dim_disease": dim_disease,
    "dim_fee_type": dim_fee_type,
    "dim_drg_group": dim_drg_group,
    "dim_visit_type": dim_visit_type,
}
