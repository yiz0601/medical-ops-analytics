"""DWS 汇总层与 ADS 集市层表结构（阶段三 · 步骤 DWS/ADS）。

    dws_dept_daily          科室 × 日期 基础度量汇总（DWS 唯一汇总表）
    ads_*_theme             8 个主题集市表（门诊/住院/收入/药品/耗材/病种/资源效率/患者服务）
    ads_indicator_result    指标结果表（指标编码 + 维度值 + 粒度 + 统计日期 唯一）

MySQL DDL 见 `sql/dws/dws_tables.sql` 与 `sql/ads/ads_tables.sql`。
"""

from __future__ import annotations

from sqlalchemy import Column, Date, DateTime, Integer, MetaData, Numeric, String, Table

MART_METADATA = MetaData()


def _dim_keys() -> list[Column]:
    """集市表统一的维度键与口径字段。"""
    return [
        Column("stat_date", Date, primary_key=True, comment="统计日期"),
        Column("dept_code", String(16), primary_key=True, comment="科室编码（ALL=全院）"),
        Column("dept_name", String(64), comment="科室名称"),
        Column("stat_ym", String(7), comment="统计年月"),
        Column("caliber", String(16), server_default="CHARGE", comment="金额口径：CHARGE 流水 / FINANCE 财务"),
        Column("etl_batch_date", Date, comment="批次业务日期"),
        Column("etl_load_time", DateTime, comment="入库时间"),
    ]


# ---------------------------------------------------------------- DWS 基础度量汇总
dws_dept_daily = Table(
    "dws_dept_daily",
    MART_METADATA,
    Column("stat_date", Date, primary_key=True, comment="统计日期"),
    Column("dept_code", String(16), primary_key=True, comment="科室编码"),
    Column("dept_name", String(64), comment="科室名称"),
    Column("stat_ym", String(7), comment="统计年月"),
    Column("bed_cnt", Integer, server_default="0", comment="开放床位数（维表快照）"),
    # 门诊度量
    Column("op_visit_cnt", Integer, server_default="0", comment="门诊人次"),
    Column("op_normal_cnt", Integer, server_default="0", comment="普通号人次"),
    Column("op_expert_cnt", Integer, server_default="0", comment="专家号人次"),
    Column("op_emergency_cnt", Integer, server_default="0", comment="急诊号人次"),
    Column("op_fee_sum", Numeric(14, 2), server_default="0", comment="门诊费用（登记口径）"),
    Column("op_patient_cnt", Integer, server_default="0", comment="门诊患者数（去重）"),
    Column("op_repeat_cnt", Integer, server_default="0", comment="复诊人次"),
    # 住院度量
    Column("ip_admit_cnt", Integer, server_default="0", comment="入院人次"),
    Column("ip_discharge_cnt", Integer, server_default="0", comment="出院人次"),
    Column("bed_days", Integer, server_default="0", comment="实际占用床日数"),
    Column("ip_fee_sum", Numeric(14, 2), server_default="0", comment="住院费用（登记口径）"),
    Column("ip_drug_fee_sum", Numeric(14, 2), server_default="0", comment="住院药品费（登记口径）"),
    Column("ip_consumable_fee_sum", Numeric(14, 2), server_default="0", comment="住院耗材费（登记口径）"),
    # 收入度量（流水口径，按收费日期归属）
    Column("charge_amt_sum", Numeric(14, 2), server_default="0", comment="收费合计"),
    Column("charge_drug_amt", Numeric(14, 2), server_default="0", comment="药品收入"),
    Column("charge_consumable_amt", Numeric(14, 2), server_default="0", comment="耗材收入"),
    Column("charge_exam_lab_amt", Numeric(14, 2), server_default="0", comment="检查检验收入"),
    Column("charge_service_amt", Numeric(14, 2), server_default="0", comment="医疗服务性收入"),
    Column("op_charge_amt", Numeric(14, 2), server_default="0", comment="门诊收入（流水）"),
    Column("ip_charge_amt", Numeric(14, 2), server_default="0", comment="住院收入（流水）"),
    # 检验度量
    Column("lis_report_cnt", Integer, server_default="0", comment="检验报告数"),
    Column("lis_abnormal_cnt", Integer, server_default="0", comment="检验异常报告数"),
    # 手术度量
    Column("ip_ss_visit_cnt", Integer, server_default="0", comment="含手术费的住院就诊数"),
    # 财务口径收入（财务日报，用于药占比/耗占比）
    Column("fin_revenue", Numeric(14, 2), server_default="0", comment="财务口径收入"),
    Column("fin_drug_revenue", Numeric(14, 2), server_default="0", comment="财务口径药品收入"),
    Column("fin_consumable_revenue", Numeric(14, 2), server_default="0", comment="财务口径耗材收入"),
    # 病种度量
    Column("drg_cases", Integer, server_default="0", comment="DRG 入组病例数"),
    Column("drg_rw_sum", Numeric(14, 2), server_default="0", comment="DRG 权重合计"),
    Column("etl_batch_date", Date, comment="批次业务日期"),
    Column("etl_load_time", DateTime, comment="入库时间"),
)

# ---------------------------------------------------------------- 8 大主题集市
ads_outpatient_theme = Table(
    "ads_outpatient_theme",
    MART_METADATA,
    Column("op_visit_cnt", Integer, server_default="0", comment="门诊人次（M01）"),
    Column("normal_cnt", Integer, server_default="0", comment="普通号人次"),
    Column("expert_cnt", Integer, server_default="0", comment="专家号人次"),
    Column("emergency_cnt", Integer, server_default="0", comment="急诊人次"),
    Column("normal_ratio", Numeric(8, 2), comment="普通号占比（M02）"),
    Column("expert_ratio", Numeric(8, 2), comment="专家号占比（M02）"),
    Column("emergency_ratio", Numeric(8, 2), comment="急诊占比（M02）"),
    Column("op_amt", Numeric(14, 2), server_default="0", comment="门诊收入（M07，流水口径）"),
    Column("op_avg_cost", Numeric(12, 2), comment="门诊次均费用（M03，登记口径）"),
    *_dim_keys(),
)

ads_inpatient_theme = Table(
    "ads_inpatient_theme",
    MART_METADATA,
    Column("ip_admit_cnt", Integer, server_default="0", comment="入院人次（M09）"),
    Column("ip_discharge_cnt", Integer, server_default="0", comment="出院人次（M08）"),
    Column("bed_days", Integer, server_default="0", comment="实际占用总床日数（M10）"),
    Column("bed_cnt", Integer, server_default="0", comment="开放床位数"),
    Column("bed_usage_rate", Numeric(8, 2), comment="床位使用率（M11，% ）"),
    Column("avg_stay_days", Numeric(8, 2), comment="平均住院日（M12）"),
    Column("ip_amt", Numeric(14, 2), server_default="0", comment="住院收入（M15，流水口径）"),
    Column("ip_avg_cost", Numeric(12, 2), comment="住院次均费用（M13，登记口径）"),
    *_dim_keys(),
)

ads_income_theme = Table(
    "ads_income_theme",
    MART_METADATA,
    Column("total_amt", Numeric(14, 2), server_default="0", comment="医疗收入合计（M16，流水口径）"),
    Column("drug_amt", Numeric(14, 2), server_default="0", comment="药品收入（M17）"),
    Column("consumable_amt", Numeric(14, 2), server_default="0", comment="耗材收入（M18）"),
    Column("exam_lab_amt", Numeric(14, 2), server_default="0", comment="检查检验收入"),
    Column("service_amt", Numeric(14, 2), server_default="0", comment="医疗服务性收入"),
    Column("drug_ratio", Numeric(8, 2), comment="药占比（M19，%）"),
    Column("consumable_ratio", Numeric(8, 2), comment="耗占比（M20，%）"),
    Column("exam_lab_ratio", Numeric(8, 2), comment="检查检验收入占比（M21，%）"),
    Column("service_ratio", Numeric(8, 2), comment="医疗服务性收入占比（M22，%）"),
    *_dim_keys(),
)

ads_drug_theme = Table(
    "ads_drug_theme",
    MART_METADATA,
    Column("drug_amt", Numeric(14, 2), server_default="0", comment="药品收入合计"),
    Column("western_amt", Numeric(14, 2), server_default="0", comment="西药费"),
    Column("patent_amt", Numeric(14, 2), server_default="0", comment="中成药费"),
    Column("drug_ratio_charge", Numeric(8, 2), comment="药占比（流水口径，%）"),
    Column("drug_ratio_finance", Numeric(8, 2), comment="药占比（财务口径，%）"),
    Column("drug_amt_per_visit", Numeric(12, 2), comment="次均药品费用"),
    *_dim_keys(),
)

ads_consumable_theme = Table(
    "ads_consumable_theme",
    MART_METADATA,
    Column("consumable_amt", Numeric(14, 2), server_default="0", comment="耗材收入"),
    Column("consumable_ratio", Numeric(8, 2), comment="耗占比（%）"),
    Column("hundred_yuan_consumable", Numeric(12, 2), comment="百元医疗收入耗材消耗（M30）"),
    Column("consumable_amt_per_discharge", Numeric(12, 2), comment="出院人次均耗材费用"),
    *_dim_keys(),
)

ads_drg_theme = Table(
    "ads_drg_theme",
    MART_METADATA,
    Column("cases", Integer, server_default="0", comment="出院病例数"),
    Column("grouped_cases", Integer, server_default="0", comment="DRG 入组病例数"),
    Column("drg_group_rate", Numeric(8, 2), comment="DRG 入组率（M23，%）"),
    Column("rw_sum", Numeric(14, 2), server_default="0", comment="权重合计"),
    Column("cmi", Numeric(8, 4), comment="CMI（M24）"),
    Column("fee_sum", Numeric(14, 2), server_default="0", comment="实际住院费用合计"),
    Column("expected_fee", Numeric(14, 2), comment="期望费用（标化基准）"),
    Column("fee_index", Numeric(8, 4), comment="费用消耗指数（M25）"),
    Column("days_sum", Integer, server_default="0", comment="实际床日合计"),
    Column("expected_days", Numeric(14, 2), comment="期望床日"),
    Column("time_index", Numeric(8, 4), comment="时间消耗指数（M26）"),
    *_dim_keys(),
)

ads_efficiency_theme = Table(
    "ads_efficiency_theme",
    MART_METADATA,
    Column("bed_cnt", Integer, server_default="0", comment="开放床位数"),
    Column("bed_usage_rate", Numeric(8, 2), comment="床位使用率（M11）"),
    Column("avg_stay_days", Numeric(8, 2), comment="平均住院日（M12）"),
    Column("income_per_bed", Numeric(14, 2), comment="每床收入"),
    Column("op_per_doctor", Numeric(12, 2), comment="医师人均门诊人次（M28，人力数据源待补）"),
    Column("bed_nurse_ratio", Numeric(8, 2), comment="床护比（M29，人力数据源待补）"),
    Column("hundred_yuan_consumable", Numeric(12, 2), comment="百元医疗收入耗材消耗（M30）"),
    *_dim_keys(),
)

ads_service_theme = Table(
    "ads_service_theme",
    MART_METADATA,
    Column("patient_cnt", Integer, server_default="0", comment="患者数（去重）"),
    Column("op_patient_cnt", Integer, server_default="0", comment="门诊患者数"),
    Column("repeat_visit_cnt", Integer, server_default="0", comment="复诊人次"),
    Column("repeat_visit_rate", Numeric(8, 2), comment="患者复诊率（M31，%）"),
    Column("lis_report_cnt", Integer, server_default="0", comment="检验报告数"),
    Column("lis_abnormal_cnt", Integer, server_default="0", comment="检验异常报告数"),
    Column("lis_abnormal_rate", Numeric(8, 2), comment="检验阳性率（M32，%）"),
    Column("emergency_ratio", Numeric(8, 2), comment="急诊人次占比（%）"),
    *_dim_keys(),
)

THEME_TABLES: dict[str, Table] = {
    "outpatient": ads_outpatient_theme,
    "inpatient": ads_inpatient_theme,
    "income": ads_income_theme,
    "drug": ads_drug_theme,
    "consumable": ads_consumable_theme,
    "drg": ads_drg_theme,
    "efficiency": ads_efficiency_theme,
    "service": ads_service_theme,
}

THEME_NAME_CN = {
    "outpatient": "门诊主题",
    "inpatient": "住院主题",
    "income": "收入主题",
    "drug": "药品主题",
    "consumable": "耗材主题",
    "drg": "病种（DRG/DIP）主题",
    "efficiency": "资源效率主题",
    "service": "患者服务主题",
}

# ---------------------------------------------------------------- 指标结果表
ads_indicator_result = Table(
    "ads_indicator_result",
    MART_METADATA,
    Column("metric_code", String(16), primary_key=True, comment="指标编码 M01~M33"),
    Column("dim_value", String(32), primary_key=True, comment="维度值（科室编码 / ALL）"),
    Column("granularity", String(16), primary_key=True, comment="粒度：day / month / period"),
    Column("stat_date", Date, primary_key=True, comment="统计日期（月粒度取月末/期初）"),
    Column("metric_name", String(64), comment="指标名称"),
    Column("theme", String(32), comment="所属主题"),
    Column("metric_value", Numeric(18, 4), comment="指标值（数据源不足时为 NULL）"),
    Column("unit", String(16), comment="单位"),
    Column("data_status", String(16), server_default="OK", comment="数据状态：OK / PENDING"),
    Column("metric_version", String(8), server_default="V1.0", comment="口径版本"),
    Column("calc_batch_id", String(32), comment="计算批次号"),
    Column("etl_load_time", DateTime, comment="计算时间"),
)

# 4 张维表（image 要求的核心维表）顺序用于校验
CORE_DIM_TABLES = ["dim_department", "dim_date", "dim_disease", "dim_fee_type"]

MART_TABLES: dict[str, Table] = {
    "dws_dept_daily": dws_dept_daily,
    **{f"ads_{k}_theme": v for k, v in THEME_TABLES.items()},
    "ads_indicator_result": ads_indicator_result,
}
