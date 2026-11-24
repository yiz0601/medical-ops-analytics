"""ODS 贴源层表结构（7 张表）。

字段与 data/ 下 7 个源 CSV 一一对应，仅追加 ETL 元数据字段：
    etl_batch_date  批次业务日期（DATE），幂等装载的删除条件
    etl_batch_id    批次标识 B+yyyyMMdd（VARCHAR），用于批次追溯
    etl_load_time   入库时间（DATETIME）

本文件是列定义的唯一实现来源；MySQL DDL 见 sql/ods/ods_tables.sql（列须与之一致）。
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

ODS_METADATA = MetaData()


def _etl_columns() -> list[Column]:
    """ETL 元数据字段（各表共用）。"""
    return [
        Column("etl_batch_date", Date, nullable=False, comment="批次业务日期（幂等删除键）"),
        Column("etl_batch_id", String(32), nullable=False, comment="批次标识 B+yyyyMMdd"),
        Column("etl_load_time", DateTime, nullable=False, comment="入库时间"),
    ]


# ---------------------------------------------------------------- HIS 门诊就诊
ods_his_outpatient_visit = Table(
    "ods_his_outpatient_visit",
    ODS_METADATA,
    Column("visit_id", String(32), nullable=False, comment="就诊号"),
    Column("patient_id", String(32), comment="患者ID"),
    Column("patient_name", String(64), comment="患者姓名（敏感）"),
    Column("id_card", String(32), comment="身份证号（敏感）"),
    Column("phone", String(32), comment="联系电话（敏感）"),
    Column("gender", String(8), comment="性别"),
    Column("age", Integer, comment="年龄"),
    Column("dept_code", String(16), comment="科室编码"),
    Column("visit_date", Date, comment="就诊日期"),
    Column("visit_type", String(16), comment="号别：普通/专家/急诊"),
    Column("fee_amount", Numeric(12, 2), comment="就诊费用（登记口径）"),
    *_etl_columns(),
    Index("idx_ods_op_visit_date", "visit_date"),
    Index("idx_ods_op_dept", "dept_code"),
    Index("idx_ods_op_batch", "etl_batch_date"),
)

# ---------------------------------------------------------------- HIS 住院就诊
ods_his_inpatient_visit = Table(
    "ods_his_inpatient_visit",
    ODS_METADATA,
    Column("visit_id", String(32), nullable=False, comment="住院号"),
    Column("patient_id", String(32), comment="患者ID"),
    Column("patient_name", String(64), comment="患者姓名（敏感）"),
    Column("id_card", String(32), comment="身份证号（敏感）"),
    Column("phone", String(32), comment="联系电话（敏感）"),
    Column("gender", String(8), comment="性别"),
    Column("age", Integer, comment="年龄"),
    Column("dept_code", String(16), comment="科室编码"),
    Column("bed_no", String(16), comment="床位号"),
    Column("admit_date", Date, comment="入院日期"),
    Column("discharge_date", Date, comment="出院日期"),
    Column("stay_days", Integer, comment="住院天数"),
    Column("total_fee", Numeric(12, 2), comment="住院总费用（登记口径）"),
    Column("drug_fee", Numeric(12, 2), comment="药品费用"),
    Column("consumable_fee", Numeric(12, 2), comment="耗材费用"),
    Column("disease_code", String(16), comment="ICD-10 主诊断编码"),
    *_etl_columns(),
    Index("idx_ods_ip_admit_date", "admit_date"),
    Index("idx_ods_ip_discharge_date", "discharge_date"),
    Index("idx_ods_ip_dept", "dept_code"),
    Index("idx_ods_ip_batch", "etl_batch_date"),
)

# ---------------------------------------------------------------- HIS 收费明细
ods_his_charge_detail = Table(
    "ods_his_charge_detail",
    ODS_METADATA,
    Column("charge_id", String(32), nullable=False, comment="收费流水号"),
    Column("visit_id", String(32), comment="就诊号"),
    Column("patient_id", String(32), comment="患者ID"),
    Column("visit_type", String(16), comment="就诊类型：门诊/住院"),
    Column("dept_code", String(16), comment="科室编码"),
    Column("fee_date", Date, comment="收费日期"),
    Column("fee_type_code", String(16), comment="费别编码"),
    Column("fee_type_name", String(32), comment="费别名称"),
    Column("amount", Numeric(12, 2), comment="金额"),
    *_etl_columns(),
    Index("idx_ods_chg_fee_date", "fee_date"),
    Index("idx_ods_chg_visit", "visit_id"),
    Index("idx_ods_chg_dept", "dept_code"),
    Index("idx_ods_chg_batch", "etl_batch_date"),
)

# ---------------------------------------------------------------- EMR 病历
ods_emr_record = Table(
    "ods_emr_record",
    ODS_METADATA,
    Column("record_id", String(32), nullable=False, comment="病历记录号"),
    Column("patient_id", String(32), comment="患者ID"),
    Column("visit_id", String(32), comment="就诊号"),
    Column("dept_code", String(16), comment="科室编码"),
    Column("visit_date", Date, comment="就诊日期"),
    Column("diagnosis", String(255), comment="诊断描述"),
    Column("disease_code", String(16), comment="ICD-10 主诊断编码"),
    *_etl_columns(),
    Index("idx_ods_emr_visit", "visit_id"),
    Index("idx_ods_emr_batch", "etl_batch_date"),
)

# ---------------------------------------------------------------- LIS 检验
ods_lis_report = Table(
    "ods_lis_report",
    ODS_METADATA,
    Column("report_id", String(32), nullable=False, comment="检验报告号"),
    Column("patient_id", String(32), comment="患者ID"),
    Column("visit_id", String(32), comment="就诊号"),
    Column("item_name", String(64), comment="检验项目"),
    Column("result_text", String(32), comment="检验结果描述"),
    Column("report_date", Date, comment="报告日期"),
    *_etl_columns(),
    Index("idx_ods_lis_visit", "visit_id"),
    Index("idx_ods_lis_batch", "etl_batch_date"),
)

# ---------------------------------------------------------------- 财务日报
ods_finance_excel = Table(
    "ods_finance_excel",
    ODS_METADATA,
    Column("record_id", String(32), nullable=False, comment="记录号"),
    Column("stat_date", Date, comment="统计日期"),
    Column("dept_code", String(16), comment="科室编码"),
    Column("revenue", Numeric(14, 2), comment="科室收入"),
    Column("drug_revenue", Numeric(14, 2), comment="药品收入"),
    Column("consumable_revenue", Numeric(14, 2), comment="耗材收入"),
    *_etl_columns(),
    Index("idx_ods_fin_stat_date", "stat_date"),
    Index("idx_ods_fin_dept", "dept_code"),
    Index("idx_ods_fin_batch", "etl_batch_date"),
)

# ---------------------------------------------------------------- 人事：科室人力台账
ods_hr_staff = Table(
    "ods_hr_staff",
    ODS_METADATA,
    Column("dept_code", String(16), nullable=False, comment="科室编码"),
    Column("dept_name", String(64), comment="科室名称"),
    Column("stat_date", Date, nullable=False, comment="台账统计日期（月末快照）"),
    Column("doctor_cnt", Integer, comment="在岗医师数"),
    Column("nurse_cnt", Integer, comment="在岗护士数"),
    *_etl_columns(),
    Index("idx_ods_hr_dept_stat", "dept_code", "stat_date"),
    Index("idx_ods_hr_batch", "etl_batch_date"),
)

# 表名 -> Table 对象，供装载与校验逻辑遍历
ODS_TABLES: dict[str, Table] = {
    "ods_his_outpatient_visit": ods_his_outpatient_visit,
    "ods_his_inpatient_visit": ods_his_inpatient_visit,
    "ods_his_charge_detail": ods_his_charge_detail,
    "ods_emr_record": ods_emr_record,
    "ods_lis_report": ods_lis_report,
    "ods_finance_excel": ods_finance_excel,
    "ods_hr_staff": ods_hr_staff,
}

# 源 CSV 列名（与 data/mock_his、data/files 表头完全一致）
ODS_SOURCE_COLUMNS: dict[str, list[str]] = {
    "ods_his_outpatient_visit": [
        "visit_id", "patient_id", "patient_name", "id_card", "phone", "gender",
        "age", "dept_code", "visit_date", "visit_type", "fee_amount",
    ],
    "ods_his_inpatient_visit": [
        "visit_id", "patient_id", "patient_name", "id_card", "phone", "gender",
        "age", "dept_code", "bed_no", "admit_date", "discharge_date", "stay_days",
        "total_fee", "drug_fee", "consumable_fee", "disease_code",
    ],
    "ods_his_charge_detail": [
        "charge_id", "visit_id", "patient_id", "visit_type", "dept_code",
        "fee_date", "fee_type_code", "fee_type_name", "amount",
    ],
    "ods_emr_record": [
        "record_id", "patient_id", "visit_id", "dept_code", "visit_date",
        "diagnosis", "disease_code",
    ],
    "ods_lis_report": [
        "report_id", "patient_id", "visit_id", "item_name", "result_text", "report_date",
    ],
    "ods_finance_excel": [
        "record_id", "stat_date", "dept_code", "revenue", "drug_revenue", "consumable_revenue",
    ],
    "ods_hr_staff": [
        "dept_code", "dept_name", "stat_date", "doctor_cnt", "nurse_cnt",
    ],
}

# 日期型与数值型源字段（读取时统一转换）
ODS_DATE_COLUMNS: dict[str, list[str]] = {
    "ods_his_outpatient_visit": ["visit_date"],
    "ods_his_inpatient_visit": ["admit_date", "discharge_date"],
    "ods_his_charge_detail": ["fee_date"],
    "ods_emr_record": ["visit_date"],
    "ods_lis_report": ["report_date"],
    "ods_finance_excel": ["stat_date"],
    "ods_hr_staff": ["stat_date"],
}

ODS_NUMERIC_COLUMNS: dict[str, list[str]] = {
    "ods_his_outpatient_visit": ["age", "fee_amount"],
    "ods_his_inpatient_visit": ["age", "stay_days", "total_fee", "drug_fee", "consumable_fee"],
    "ods_his_charge_detail": ["amount"],
    "ods_emr_record": [],
    "ods_lis_report": [],
    "ods_finance_excel": ["revenue", "drug_revenue", "consumable_revenue"],
    "ods_hr_staff": ["doctor_cnt", "nurse_cnt"],
}

ODS_INT_COLUMNS: dict[str, list[str]] = {
    "ods_his_outpatient_visit": ["age"],
    "ods_his_inpatient_visit": ["age", "stay_days"],
    "ods_his_charge_detail": [],
    "ods_emr_record": [],
    "ods_lis_report": [],
    "ods_finance_excel": [],
    "ods_hr_staff": ["doctor_cnt", "nurse_cnt"],
}
