-- =============================================================================
-- 医疗运营数据主题分析平台 —— ADS 集市层建表脚本（阶段三 · 集市步骤 2）
-- 本文件由 backend/etl/jobs/export_ddl.py 自动生成，请勿手工编辑。
-- 来源：backend/etl/config/mart_schema.py
-- 数据库：MySQL 8.0    字符集：utf8mb4    引擎：InnoDB
-- 执行：mysql -h127.0.0.1 -uroot -p < sql/ads/ads_tables.sql
-- =============================================================================

CREATE DATABASE IF NOT EXISTS medical_ops
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_general_ci;

USE medical_ops;

-- 说明：8 个主题集市表（主键唯一：科室码 + 日期）+ 指标结果表
--       ads_indicator_result 唯一键 = 指标编码 + 维度值 + 粒度 + 统计日期

-- ---------------------------------------------------------------- ads_outpatient_theme
CREATE TABLE IF NOT EXISTS ads_outpatient_theme (
	op_visit_cnt INTEGER DEFAULT '0' COMMENT '门诊人次（M01）',
	normal_cnt INTEGER DEFAULT '0' COMMENT '普通号人次',
	expert_cnt INTEGER DEFAULT '0' COMMENT '专家号人次',
	emergency_cnt INTEGER DEFAULT '0' COMMENT '急诊人次',
	normal_ratio NUMERIC(8, 2) COMMENT '普通号占比（M02）',
	expert_ratio NUMERIC(8, 2) COMMENT '专家号占比（M02）',
	emergency_ratio NUMERIC(8, 2) COMMENT '急诊占比（M02）',
	op_amt NUMERIC(14, 2) DEFAULT '0' COMMENT '门诊收入（M07，流水口径）',
	op_avg_cost NUMERIC(12, 2) COMMENT '门诊次均费用（M03，登记口径）',
	stat_date DATE NOT NULL COMMENT '统计日期',
	dept_code VARCHAR(16) NOT NULL COMMENT '科室编码（ALL=全院）',
	dept_name VARCHAR(64) COMMENT '科室名称',
	stat_ym VARCHAR(7) COMMENT '统计年月',
	caliber VARCHAR(16) DEFAULT 'CHARGE' COMMENT '金额口径：CHARGE 流水 / FINANCE 财务',
	etl_batch_date DATE COMMENT '批次业务日期',
	etl_load_time DATETIME COMMENT '入库时间',
	PRIMARY KEY (stat_date, dept_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------- ads_inpatient_theme
CREATE TABLE IF NOT EXISTS ads_inpatient_theme (
	ip_admit_cnt INTEGER DEFAULT '0' COMMENT '入院人次（M09）',
	ip_discharge_cnt INTEGER DEFAULT '0' COMMENT '出院人次（M08）',
	bed_days INTEGER DEFAULT '0' COMMENT '实际占用总床日数（M10）',
	bed_cnt INTEGER DEFAULT '0' COMMENT '开放床位数',
	bed_usage_rate NUMERIC(8, 2) COMMENT '床位使用率（M11，%% ）',
	avg_stay_days NUMERIC(8, 2) COMMENT '平均住院日（M12）',
	ip_amt NUMERIC(14, 2) DEFAULT '0' COMMENT '住院收入（M15，流水口径）',
	ip_avg_cost NUMERIC(12, 2) COMMENT '住院次均费用（M13，登记口径）',
	stat_date DATE NOT NULL COMMENT '统计日期',
	dept_code VARCHAR(16) NOT NULL COMMENT '科室编码（ALL=全院）',
	dept_name VARCHAR(64) COMMENT '科室名称',
	stat_ym VARCHAR(7) COMMENT '统计年月',
	caliber VARCHAR(16) DEFAULT 'CHARGE' COMMENT '金额口径：CHARGE 流水 / FINANCE 财务',
	etl_batch_date DATE COMMENT '批次业务日期',
	etl_load_time DATETIME COMMENT '入库时间',
	PRIMARY KEY (stat_date, dept_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------- ads_income_theme
CREATE TABLE IF NOT EXISTS ads_income_theme (
	total_amt NUMERIC(14, 2) DEFAULT '0' COMMENT '医疗收入合计（M16，流水口径）',
	drug_amt NUMERIC(14, 2) DEFAULT '0' COMMENT '药品收入（M17）',
	consumable_amt NUMERIC(14, 2) DEFAULT '0' COMMENT '耗材收入（M18）',
	exam_lab_amt NUMERIC(14, 2) DEFAULT '0' COMMENT '检查检验收入',
	service_amt NUMERIC(14, 2) DEFAULT '0' COMMENT '医疗服务性收入',
	drug_ratio NUMERIC(8, 2) COMMENT '药占比（M19，%%）',
	consumable_ratio NUMERIC(8, 2) COMMENT '耗占比（M20，%%）',
	exam_lab_ratio NUMERIC(8, 2) COMMENT '检查检验收入占比（M21，%%）',
	service_ratio NUMERIC(8, 2) COMMENT '医疗服务性收入占比（M22，%%）',
	stat_date DATE NOT NULL COMMENT '统计日期',
	dept_code VARCHAR(16) NOT NULL COMMENT '科室编码（ALL=全院）',
	dept_name VARCHAR(64) COMMENT '科室名称',
	stat_ym VARCHAR(7) COMMENT '统计年月',
	caliber VARCHAR(16) DEFAULT 'CHARGE' COMMENT '金额口径：CHARGE 流水 / FINANCE 财务',
	etl_batch_date DATE COMMENT '批次业务日期',
	etl_load_time DATETIME COMMENT '入库时间',
	PRIMARY KEY (stat_date, dept_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------- ads_drug_theme
CREATE TABLE IF NOT EXISTS ads_drug_theme (
	drug_amt NUMERIC(14, 2) DEFAULT '0' COMMENT '药品收入合计',
	western_amt NUMERIC(14, 2) DEFAULT '0' COMMENT '西药费',
	patent_amt NUMERIC(14, 2) DEFAULT '0' COMMENT '中成药费',
	drug_ratio_charge NUMERIC(8, 2) COMMENT '药占比（流水口径，%%）',
	drug_ratio_finance NUMERIC(8, 2) COMMENT '药占比（财务口径，%%）',
	drug_amt_per_visit NUMERIC(12, 2) COMMENT '次均药品费用',
	stat_date DATE NOT NULL COMMENT '统计日期',
	dept_code VARCHAR(16) NOT NULL COMMENT '科室编码（ALL=全院）',
	dept_name VARCHAR(64) COMMENT '科室名称',
	stat_ym VARCHAR(7) COMMENT '统计年月',
	caliber VARCHAR(16) DEFAULT 'CHARGE' COMMENT '金额口径：CHARGE 流水 / FINANCE 财务',
	etl_batch_date DATE COMMENT '批次业务日期',
	etl_load_time DATETIME COMMENT '入库时间',
	PRIMARY KEY (stat_date, dept_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------- ads_consumable_theme
CREATE TABLE IF NOT EXISTS ads_consumable_theme (
	consumable_amt NUMERIC(14, 2) DEFAULT '0' COMMENT '耗材收入',
	consumable_ratio NUMERIC(8, 2) COMMENT '耗占比（%%）',
	hundred_yuan_consumable NUMERIC(12, 2) COMMENT '百元医疗收入耗材消耗（M30）',
	consumable_amt_per_discharge NUMERIC(12, 2) COMMENT '出院人次均耗材费用',
	stat_date DATE NOT NULL COMMENT '统计日期',
	dept_code VARCHAR(16) NOT NULL COMMENT '科室编码（ALL=全院）',
	dept_name VARCHAR(64) COMMENT '科室名称',
	stat_ym VARCHAR(7) COMMENT '统计年月',
	caliber VARCHAR(16) DEFAULT 'CHARGE' COMMENT '金额口径：CHARGE 流水 / FINANCE 财务',
	etl_batch_date DATE COMMENT '批次业务日期',
	etl_load_time DATETIME COMMENT '入库时间',
	PRIMARY KEY (stat_date, dept_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------- ads_drg_theme
CREATE TABLE IF NOT EXISTS ads_drg_theme (
	cases INTEGER DEFAULT '0' COMMENT '出院病例数',
	grouped_cases INTEGER DEFAULT '0' COMMENT 'DRG 入组病例数',
	drg_group_rate NUMERIC(8, 2) COMMENT 'DRG 入组率（M23，%%）',
	rw_sum NUMERIC(14, 2) DEFAULT '0' COMMENT '权重合计',
	cmi NUMERIC(8, 4) COMMENT 'CMI（M24）',
	fee_sum NUMERIC(14, 2) DEFAULT '0' COMMENT '实际住院费用合计',
	expected_fee NUMERIC(14, 2) COMMENT '期望费用（标化基准）',
	fee_index NUMERIC(8, 4) COMMENT '费用消耗指数（M25）',
	days_sum INTEGER DEFAULT '0' COMMENT '实际床日合计',
	expected_days NUMERIC(14, 2) COMMENT '期望床日',
	time_index NUMERIC(8, 4) COMMENT '时间消耗指数（M26）',
	stat_date DATE NOT NULL COMMENT '统计日期',
	dept_code VARCHAR(16) NOT NULL COMMENT '科室编码（ALL=全院）',
	dept_name VARCHAR(64) COMMENT '科室名称',
	stat_ym VARCHAR(7) COMMENT '统计年月',
	caliber VARCHAR(16) DEFAULT 'CHARGE' COMMENT '金额口径：CHARGE 流水 / FINANCE 财务',
	etl_batch_date DATE COMMENT '批次业务日期',
	etl_load_time DATETIME COMMENT '入库时间',
	PRIMARY KEY (stat_date, dept_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------- ads_efficiency_theme
CREATE TABLE IF NOT EXISTS ads_efficiency_theme (
	bed_cnt INTEGER DEFAULT '0' COMMENT '开放床位数',
	bed_usage_rate NUMERIC(8, 2) COMMENT '床位使用率（M11）',
	avg_stay_days NUMERIC(8, 2) COMMENT '平均住院日（M12）',
	income_per_bed NUMERIC(14, 2) COMMENT '每床收入',
	op_per_doctor NUMERIC(12, 2) COMMENT '医师人均门诊人次（M28，人力数据源待补）',
	bed_nurse_ratio NUMERIC(8, 2) COMMENT '床护比（M29，人力数据源待补）',
	hundred_yuan_consumable NUMERIC(12, 2) COMMENT '百元医疗收入耗材消耗（M30）',
	stat_date DATE NOT NULL COMMENT '统计日期',
	dept_code VARCHAR(16) NOT NULL COMMENT '科室编码（ALL=全院）',
	dept_name VARCHAR(64) COMMENT '科室名称',
	stat_ym VARCHAR(7) COMMENT '统计年月',
	caliber VARCHAR(16) DEFAULT 'CHARGE' COMMENT '金额口径：CHARGE 流水 / FINANCE 财务',
	etl_batch_date DATE COMMENT '批次业务日期',
	etl_load_time DATETIME COMMENT '入库时间',
	PRIMARY KEY (stat_date, dept_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------- ads_service_theme
CREATE TABLE IF NOT EXISTS ads_service_theme (
	patient_cnt INTEGER DEFAULT '0' COMMENT '患者数（去重）',
	op_patient_cnt INTEGER DEFAULT '0' COMMENT '门诊患者数',
	repeat_visit_cnt INTEGER DEFAULT '0' COMMENT '复诊人次',
	repeat_visit_rate NUMERIC(8, 2) COMMENT '患者复诊率（M31，%%）',
	lis_report_cnt INTEGER DEFAULT '0' COMMENT '检验报告数',
	lis_abnormal_cnt INTEGER DEFAULT '0' COMMENT '检验异常报告数',
	lis_abnormal_rate NUMERIC(8, 2) COMMENT '检验阳性率（M32，%%）',
	emergency_ratio NUMERIC(8, 2) COMMENT '急诊人次占比（%%）',
	stat_date DATE NOT NULL COMMENT '统计日期',
	dept_code VARCHAR(16) NOT NULL COMMENT '科室编码（ALL=全院）',
	dept_name VARCHAR(64) COMMENT '科室名称',
	stat_ym VARCHAR(7) COMMENT '统计年月',
	caliber VARCHAR(16) DEFAULT 'CHARGE' COMMENT '金额口径：CHARGE 流水 / FINANCE 财务',
	etl_batch_date DATE COMMENT '批次业务日期',
	etl_load_time DATETIME COMMENT '入库时间',
	PRIMARY KEY (stat_date, dept_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------- ads_indicator_result
CREATE TABLE IF NOT EXISTS ads_indicator_result (
	metric_code VARCHAR(16) NOT NULL COMMENT '指标编码 M01~M33',
	dim_value VARCHAR(32) NOT NULL COMMENT '维度值（科室编码 / ALL）',
	granularity VARCHAR(16) NOT NULL COMMENT '粒度：day / month / period',
	stat_date DATE NOT NULL COMMENT '统计日期（月粒度取月末/期初）',
	metric_name VARCHAR(64) COMMENT '指标名称',
	theme VARCHAR(32) COMMENT '所属主题',
	metric_value NUMERIC(18, 4) COMMENT '指标值（数据源不足时为 NULL）',
	unit VARCHAR(16) COMMENT '单位',
	data_status VARCHAR(16) DEFAULT 'OK' COMMENT '数据状态：OK / PENDING',
	metric_version VARCHAR(8) DEFAULT 'V1.0' COMMENT '口径版本',
	calc_batch_id VARCHAR(32) COMMENT '计算批次号',
	etl_load_time DATETIME COMMENT '计算时间',
	PRIMARY KEY (metric_code, dim_value, granularity, stat_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
