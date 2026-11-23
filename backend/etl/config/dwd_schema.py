"""DWD 明细层表结构（5 张规范表 + 1 张财务扩展表）。

设计约定：
    * 主键与 ODS 一致（1 业务事件 1 行），并追加 etl_batch_date / etl_batch_id / etl_load_time
    * 隐私字段一律脱敏：patient_name -> patient_name_masked，id_card -> id_card_masked，
      phone -> phone_masked；原值仅保留在 ODS 层（仅 DBA 与 ETL 账号可读）
    * 追加派生列：dept_name、visit_ym、age_group、visit_type_code、
      fee_class（费别归类）、disease_name、drg_code、rw、result_flag

MySQL DDL 见 sql/dwd/dwd_tables.sql（列须与之一致）。
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
)

DWD_METADATA = MetaData()


def _etl_columns() -> list[Column]:
    return [
        Column("etl_batch_date", Date, nullable=False, comment="批次业务日期"),
        Column("etl_batch_id", String(32), nullable=False, comment="批次标识 B+yyyyMMdd"),
        Column("etl_load_time", DateTime, nullable=False, comment="入库时间"),
    ]


# ---------------------------------------------------------------- 门诊就诊明细
dwd_outpatient_visit_detail = Table(
    "dwd_outpatient_visit_detail",
    DWD_METADATA,
    Column("visit_id", String(32), primary_key=True, comment="就诊号"),
    Column("patient_id", String(32), comment="患者ID"),
    Column("patient_name_masked", String(64), comment="姓名（脱敏）"),
    Column("id_card_masked", String(32), comment="身份证号（脱敏）"),
    Column("phone_masked", String(32), comment="手机号（脱敏）"),
    Column("gender", String(8), comment="性别"),
    Column("age", Integer, comment="年龄"),
    Column("age_group", String(16), comment="年龄段"),
    Column("dept_code", String(16), comment="科室编码"),
    Column("dept_name", String(64), comment="科室名称"),
    Column("visit_date", Date, comment="就诊日期"),
    Column("visit_ym", String(7), comment="就诊年月 YYYY-MM"),
    Column("visit_type", String(16), comment="号别"),
    Column("visit_type_code", String(8), comment="号别编码"),
    Column("fee_amount", Numeric(12, 2), comment="就诊费用（登记口径）"),
    *_etl_columns(),
    Index("idx_dwd_op_date", "visit_date"),
    Index("idx_dwd_op_dept", "dept_code"),
    Index("idx_dwd_op_patient", "patient_id"),
    Index("idx_dwd_op_batch", "etl_batch_date"),
)

# ---------------------------------------------------------------- 住院就诊明细
dwd_inpatient_visit_detail = Table(
    "dwd_inpatient_visit_detail",
    DWD_METADATA,
    Column("visit_id", String(32), primary_key=True, comment="住院号"),
    Column("patient_id", String(32), comment="患者ID"),
    Column("patient_name_masked", String(64), comment="姓名（脱敏）"),
    Column("id_card_masked", String(32), comment="身份证号（脱敏）"),
    Column("phone_masked", String(32), comment="手机号（脱敏）"),
    Column("gender", String(8), comment="性别"),
    Column("age", Integer, comment="年龄"),
    Column("age_group", String(16), comment="年龄段"),
    Column("dept_code", String(16), comment="科室编码"),
    Column("dept_name", String(64), comment="科室名称"),
    Column("bed_no", String(16), comment="床位号"),
    Column("admit_date", Date, comment="入院日期"),
    Column("discharge_date", Date, comment="出院日期"),
    Column("stay_days", Integer, comment="住院天数"),
    Column("total_fee", Numeric(12, 2), comment="住院总费用（登记口径）"),
    Column("drug_fee", Numeric(12, 2), comment="药品费用"),
    Column("consumable_fee", Numeric(12, 2), comment="耗材费用"),
    Column("disease_code", String(16), comment="ICD-10 主诊断编码"),
    Column("disease_name", String(64), comment="病种名称"),
    Column("drg_code", String(16), comment="DRG 组编码（模拟分组）"),
    Column("rw", Numeric(6, 2), comment="DRG 权重 RW"),
    *_etl_columns(),
    Index("idx_dwd_ip_admit", "admit_date"),
    Index("idx_dwd_ip_discharge", "discharge_date"),
    Index("idx_dwd_ip_dept", "dept_code"),
    Index("idx_dwd_ip_disease", "disease_code"),
    Index("idx_dwd_ip_batch", "etl_batch_date"),
)

# ---------------------------------------------------------------- 收费明细
dwd_charge_detail = Table(
    "dwd_charge_detail",
    DWD_METADATA,
    Column("charge_id", String(32), primary_key=True, comment="收费流水号"),
    Column("visit_id", String(32), comment="就诊号"),
    Column("patient_id", String(32), comment="患者ID"),
    Column("visit_type", String(16), comment="就诊类型：门诊/住院"),
    Column("visit_type_code", String(8), comment="就诊类型编码"),
    Column("dept_code", String(16), comment="科室编码"),
    Column("dept_name", String(64), comment="科室名称"),
    Column("fee_date", Date, comment="收费日期"),
    Column("fee_ym", String(7), comment="收费年月 YYYY-MM"),
    Column("fee_type_code", String(16), comment="费别编码"),
    Column("fee_type_name", String(32), comment="费别名称"),
    Column("fee_class", String(32), comment="费别归类：药品/耗材/检查检验/医疗服务性"),
    Column("amount", Numeric(12, 2), comment="金额"),
    *_etl_columns(),
    Index("idx_dwd_chg_date", "fee_date"),
    Index("idx_dwd_chg_visit", "visit_id"),
    Index("idx_dwd_chg_dept", "dept_code"),
    Index("idx_dwd_chg_class", "fee_class"),
    Index("idx_dwd_chg_batch", "etl_batch_date"),
)

# ---------------------------------------------------------------- 病历明细
dwd_emr_record_detail = Table(
    "dwd_emr_record_detail",
    DWD_METADATA,
    Column("record_id", String(32), primary_key=True, comment="病历记录号"),
    Column("patient_id", String(32), comment="患者ID"),
    Column("visit_id", String(32), comment="就诊号"),
    Column("dept_code", String(16), comment="科室编码"),
    Column("dept_name", String(64), comment="科室名称"),
    Column("visit_date", Date, comment="就诊日期"),
    Column("diagnosis", String(255), comment="诊断描述"),
    Column("disease_code", String(16), comment="ICD-10 编码"),
    Column("disease_name", String(64), comment="病种名称"),
    Column("drg_code", String(16), comment="DRG 组编码（模拟分组）"),
    *_etl_columns(),
    Index("idx_dwd_emr_visit", "visit_id"),
    Index("idx_dwd_emr_disease", "disease_code"),
    Index("idx_dwd_emr_batch", "etl_batch_date"),
)

# ---------------------------------------------------------------- 检验明细
dwd_lis_report_detail = Table(
    "dwd_lis_report_detail",
    DWD_METADATA,
    Column("report_id", String(32), primary_key=True, comment="检验报告号"),
    Column("patient_id", String(32), comment="患者ID"),
    Column("visit_id", String(32), comment="就诊号"),
    Column("item_name", String(64), comment="检验项目"),
    Column("result_text", String(32), comment="检验结果描述"),
    Column("result_flag", String(16), comment="结果判定：正常/异常"),
    Column("report_date", Date, comment="报告日期"),
    *_etl_columns(),
    Index("idx_dwd_lis_visit", "visit_id"),
    Index("idx_dwd_lis_flag", "result_flag"),
    Index("idx_dwd_lis_batch", "etl_batch_date"),
)

# ---------------------------------------------------------------- 财务日报（扩展）
dwd_finance_daily_detail = Table(
    "dwd_finance_daily_detail",
    DWD_METADATA,
    Column("record_id", String(32), primary_key=True, comment="记录号"),
    Column("stat_date", Date, comment="统计日期"),
    Column("stat_ym", String(7), comment="统计年月 YYYY-MM"),
    Column("dept_code", String(16), comment="科室编码"),
    Column("dept_name", String(64), comment="科室名称"),
    Column("revenue", Numeric(14, 2), comment="科室收入"),
    Column("drug_revenue", Numeric(14, 2), comment="药品收入"),
    Column("consumable_revenue", Numeric(14, 2), comment="耗材收入"),
    *_etl_columns(),
    Index("idx_dwd_fin_date", "stat_date"),
    Index("idx_dwd_fin_dept", "dept_code"),
    Index("idx_dwd_fin_batch", "etl_batch_date"),
)

DWD_TABLES: dict[str, Table] = {
    "dwd_outpatient_visit_detail": dwd_outpatient_visit_detail,
    "dwd_inpatient_visit_detail": dwd_inpatient_visit_detail,
    "dwd_charge_detail": dwd_charge_detail,
    "dwd_emr_record_detail": dwd_emr_record_detail,
    "dwd_lis_report_detail": dwd_lis_report_detail,
    "dwd_finance_daily_detail": dwd_finance_daily_detail,
}
