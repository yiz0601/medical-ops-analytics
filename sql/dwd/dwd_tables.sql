-- =============================================================================
-- 医疗运营数据主题分析平台 —— DWD 明细层建表脚本（阶段二/三 · 步骤 3）
-- 本文件由 backend/etl/jobs/export_ddl.py 自动生成，请勿手工编辑。
-- 来源：backend/etl/config/dwd_schema.py
-- 数据库：MySQL 8.0    字符集：utf8mb4    引擎：InnoDB
-- 执行：mysql -h127.0.0.1 -uroot -p < sql/dwd/dwd_tables.sql
-- =============================================================================

CREATE DATABASE IF NOT EXISTS medical_ops
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_general_ci;

USE medical_ops;

-- 说明：ODS 经去重、填充、编码标准化、隐私脱敏后写入本层；
--       dwd_visit_detail 为门诊+住院统一就诊宽表，dwd_charge_detail 为收费宽表（关联科室与标准收费类别码）

-- ---------------------------------------------------------------- dwd_visit_detail
CREATE TABLE IF NOT EXISTS dwd_visit_detail (
	visit_id VARCHAR(32) NOT NULL COMMENT '就诊号（门诊 OV* / 住院 IV*）',
	visit_type VARCHAR(16) COMMENT '就诊类型：门诊/住院',
	visit_type_code VARCHAR(8) COMMENT '类型编码 OPD/IPD',
	patient_id VARCHAR(32) COMMENT '患者ID',
	patient_name_masked VARCHAR(64) COMMENT '姓名（脱敏）',
	gender VARCHAR(8) COMMENT '性别',
	age INTEGER COMMENT '年龄',
	age_group VARCHAR(16) COMMENT '年龄段',
	dept_code VARCHAR(16) COMMENT '科室编码',
	dept_name VARCHAR(64) COMMENT '科室名称',
	dept_parent_code VARCHAR(16) COMMENT '上级科室系编码',
	org_area VARCHAR(32) COMMENT '院区',
	visit_date DATE COMMENT '就诊日期 / 入院日期',
	visit_ym VARCHAR(7) COMMENT '就诊年月 YYYY-MM',
	discharge_date DATE COMMENT '出院日期（门诊为空）',
	stay_days INTEGER COMMENT '住院天数（门诊为空）',
	bed_no VARCHAR(16) COMMENT '床位号（门诊为空）',
	disease_code VARCHAR(16) COMMENT 'ICD-10 主诊断',
	disease_name VARCHAR(64) COMMENT '病种名称',
	drg_code VARCHAR(16) COMMENT 'DRG 组编码（模拟分组）',
	rw NUMERIC(6, 2) COMMENT 'DRG 权重 RW',
	total_fee NUMERIC(12, 2) COMMENT '登记口径总费用',
	drug_fee NUMERIC(12, 2) COMMENT '登记口径药品费',
	consumable_fee NUMERIC(12, 2) COMMENT '登记口径耗材费',
	charge_amt_total NUMERIC(14, 2) COMMENT '流水口径合计金额',
	charge_drug_amt NUMERIC(14, 2) COMMENT '流水口径药品收入',
	charge_consumable_amt NUMERIC(14, 2) COMMENT '流水口径耗材收入',
	charge_exam_lab_amt NUMERIC(14, 2) COMMENT '流水口径检查检验收入',
	charge_service_amt NUMERIC(14, 2) COMMENT '流水口径医疗服务性收入',
	drug_ratio NUMERIC(8, 4) COMMENT '药品收入占流水比',
	consumable_ratio NUMERIC(8, 4) COMMENT '耗材收入占流水比',
	etl_batch_date DATE NOT NULL COMMENT '批次业务日期',
	etl_batch_id VARCHAR(32) NOT NULL COMMENT '批次标识 B+yyyyMMdd',
	etl_load_time DATETIME NOT NULL COMMENT '入库时间',
	PRIMARY KEY (visit_id),
	KEY idx_dwd_visit_batch (etl_batch_date),
	KEY idx_dwd_visit_date (visit_date),
	KEY idx_dwd_visit_dept (dept_code),
	KEY idx_dwd_visit_disease (disease_code),
	KEY idx_dwd_visit_type (visit_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------- dwd_outpatient_visit_detail
CREATE TABLE IF NOT EXISTS dwd_outpatient_visit_detail (
	visit_id VARCHAR(32) NOT NULL COMMENT '就诊号',
	patient_id VARCHAR(32) COMMENT '患者ID',
	patient_name_masked VARCHAR(64) COMMENT '姓名（脱敏）',
	id_card_masked VARCHAR(32) COMMENT '身份证号（脱敏）',
	phone_masked VARCHAR(32) COMMENT '手机号（脱敏）',
	gender VARCHAR(8) COMMENT '性别',
	age INTEGER COMMENT '年龄',
	age_group VARCHAR(16) COMMENT '年龄段',
	dept_code VARCHAR(16) COMMENT '科室编码',
	dept_name VARCHAR(64) COMMENT '科室名称',
	visit_date DATE COMMENT '就诊日期',
	visit_ym VARCHAR(7) COMMENT '就诊年月 YYYY-MM',
	visit_type VARCHAR(16) COMMENT '号别',
	visit_type_code VARCHAR(8) COMMENT '号别编码',
	fee_amount NUMERIC(12, 2) COMMENT '就诊费用（登记口径）',
	etl_batch_date DATE NOT NULL COMMENT '批次业务日期',
	etl_batch_id VARCHAR(32) NOT NULL COMMENT '批次标识 B+yyyyMMdd',
	etl_load_time DATETIME NOT NULL COMMENT '入库时间',
	PRIMARY KEY (visit_id),
	KEY idx_dwd_op_batch (etl_batch_date),
	KEY idx_dwd_op_date (visit_date),
	KEY idx_dwd_op_dept (dept_code),
	KEY idx_dwd_op_patient (patient_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------- dwd_inpatient_visit_detail
CREATE TABLE IF NOT EXISTS dwd_inpatient_visit_detail (
	visit_id VARCHAR(32) NOT NULL COMMENT '住院号',
	patient_id VARCHAR(32) COMMENT '患者ID',
	patient_name_masked VARCHAR(64) COMMENT '姓名（脱敏）',
	id_card_masked VARCHAR(32) COMMENT '身份证号（脱敏）',
	phone_masked VARCHAR(32) COMMENT '手机号（脱敏）',
	gender VARCHAR(8) COMMENT '性别',
	age INTEGER COMMENT '年龄',
	age_group VARCHAR(16) COMMENT '年龄段',
	dept_code VARCHAR(16) COMMENT '科室编码',
	dept_name VARCHAR(64) COMMENT '科室名称',
	bed_no VARCHAR(16) COMMENT '床位号',
	admit_date DATE COMMENT '入院日期',
	discharge_date DATE COMMENT '出院日期',
	stay_days INTEGER COMMENT '住院天数',
	total_fee NUMERIC(12, 2) COMMENT '住院总费用（登记口径）',
	drug_fee NUMERIC(12, 2) COMMENT '药品费用',
	consumable_fee NUMERIC(12, 2) COMMENT '耗材费用',
	disease_code VARCHAR(16) COMMENT 'ICD-10 主诊断编码',
	disease_name VARCHAR(64) COMMENT '病种名称',
	drg_code VARCHAR(16) COMMENT 'DRG 组编码（模拟分组）',
	rw NUMERIC(6, 2) COMMENT 'DRG 权重 RW',
	etl_batch_date DATE NOT NULL COMMENT '批次业务日期',
	etl_batch_id VARCHAR(32) NOT NULL COMMENT '批次标识 B+yyyyMMdd',
	etl_load_time DATETIME NOT NULL COMMENT '入库时间',
	PRIMARY KEY (visit_id),
	KEY idx_dwd_ip_admit (admit_date),
	KEY idx_dwd_ip_batch (etl_batch_date),
	KEY idx_dwd_ip_dept (dept_code),
	KEY idx_dwd_ip_discharge (discharge_date),
	KEY idx_dwd_ip_disease (disease_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------- dwd_charge_detail
CREATE TABLE IF NOT EXISTS dwd_charge_detail (
	charge_id VARCHAR(32) NOT NULL COMMENT '收费流水号',
	visit_id VARCHAR(32) COMMENT '就诊号',
	patient_id VARCHAR(32) COMMENT '患者ID',
	visit_type VARCHAR(16) COMMENT '就诊类型：门诊/住院',
	visit_type_code VARCHAR(8) COMMENT '就诊类型编码',
	dept_code VARCHAR(16) COMMENT '科室编码',
	dept_name VARCHAR(64) COMMENT '科室名称',
	dept_parent_code VARCHAR(16) COMMENT '上级科室系编码（关联 dim_department）',
	fee_date DATE COMMENT '收费日期',
	fee_ym VARCHAR(7) COMMENT '收费年月 YYYY-MM',
	fee_type_code VARCHAR(16) COMMENT '费别编码',
	fee_type_name VARCHAR(32) COMMENT '费别名称',
	fee_std_code VARCHAR(16) COMMENT '标准收费类别码（关联 dim_fee_type）',
	fee_std_name VARCHAR(32) COMMENT '标准收费类别名称',
	is_drug INTEGER DEFAULT '0' COMMENT '是否药品',
	is_consumable INTEGER DEFAULT '0' COMMENT '是否耗材',
	fee_class VARCHAR(32) COMMENT '费别归类：药品/耗材/检查检验/医疗服务性',
	amount NUMERIC(12, 2) COMMENT '金额',
	etl_batch_date DATE NOT NULL COMMENT '批次业务日期',
	etl_batch_id VARCHAR(32) NOT NULL COMMENT '批次标识 B+yyyyMMdd',
	etl_load_time DATETIME NOT NULL COMMENT '入库时间',
	PRIMARY KEY (charge_id),
	KEY idx_dwd_chg_batch (etl_batch_date),
	KEY idx_dwd_chg_class (fee_class),
	KEY idx_dwd_chg_date (fee_date),
	KEY idx_dwd_chg_dept (dept_code),
	KEY idx_dwd_chg_visit (visit_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------- dwd_emr_record_detail
CREATE TABLE IF NOT EXISTS dwd_emr_record_detail (
	record_id VARCHAR(32) NOT NULL COMMENT '病历记录号',
	patient_id VARCHAR(32) COMMENT '患者ID',
	visit_id VARCHAR(32) COMMENT '就诊号',
	dept_code VARCHAR(16) COMMENT '科室编码',
	dept_name VARCHAR(64) COMMENT '科室名称',
	visit_date DATE COMMENT '就诊日期',
	diagnosis VARCHAR(255) COMMENT '诊断描述',
	disease_code VARCHAR(16) COMMENT 'ICD-10 编码',
	disease_name VARCHAR(64) COMMENT '病种名称',
	drg_code VARCHAR(16) COMMENT 'DRG 组编码（模拟分组）',
	etl_batch_date DATE NOT NULL COMMENT '批次业务日期',
	etl_batch_id VARCHAR(32) NOT NULL COMMENT '批次标识 B+yyyyMMdd',
	etl_load_time DATETIME NOT NULL COMMENT '入库时间',
	PRIMARY KEY (record_id),
	KEY idx_dwd_emr_batch (etl_batch_date),
	KEY idx_dwd_emr_disease (disease_code),
	KEY idx_dwd_emr_visit (visit_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------- dwd_lis_report_detail
CREATE TABLE IF NOT EXISTS dwd_lis_report_detail (
	report_id VARCHAR(32) NOT NULL COMMENT '检验报告号',
	patient_id VARCHAR(32) COMMENT '患者ID',
	visit_id VARCHAR(32) COMMENT '就诊号',
	item_name VARCHAR(64) COMMENT '检验项目',
	result_text VARCHAR(32) COMMENT '检验结果描述',
	result_flag VARCHAR(16) COMMENT '结果判定：正常/异常',
	report_date DATE COMMENT '报告日期',
	etl_batch_date DATE NOT NULL COMMENT '批次业务日期',
	etl_batch_id VARCHAR(32) NOT NULL COMMENT '批次标识 B+yyyyMMdd',
	etl_load_time DATETIME NOT NULL COMMENT '入库时间',
	PRIMARY KEY (report_id),
	KEY idx_dwd_lis_batch (etl_batch_date),
	KEY idx_dwd_lis_flag (result_flag),
	KEY idx_dwd_lis_visit (visit_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------- dwd_finance_daily_detail
CREATE TABLE IF NOT EXISTS dwd_finance_daily_detail (
	record_id VARCHAR(32) NOT NULL COMMENT '记录号',
	stat_date DATE COMMENT '统计日期',
	stat_ym VARCHAR(7) COMMENT '统计年月 YYYY-MM',
	dept_code VARCHAR(16) COMMENT '科室编码',
	dept_name VARCHAR(64) COMMENT '科室名称',
	revenue NUMERIC(14, 2) COMMENT '科室收入',
	drug_revenue NUMERIC(14, 2) COMMENT '药品收入',
	consumable_revenue NUMERIC(14, 2) COMMENT '耗材收入',
	etl_batch_date DATE NOT NULL COMMENT '批次业务日期',
	etl_batch_id VARCHAR(32) NOT NULL COMMENT '批次标识 B+yyyyMMdd',
	etl_load_time DATETIME NOT NULL COMMENT '入库时间',
	PRIMARY KEY (record_id),
	KEY idx_dwd_fin_batch (etl_batch_date),
	KEY idx_dwd_fin_date (stat_date),
	KEY idx_dwd_fin_dept (dept_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------- dwd_hr_staff_detail
CREATE TABLE IF NOT EXISTS dwd_hr_staff_detail (
	dept_code VARCHAR(16) NOT NULL COMMENT '科室编码',
	stat_date DATE NOT NULL COMMENT '台账统计日期',
	dept_name VARCHAR(64) COMMENT '科室名称',
	dept_parent_code VARCHAR(16) COMMENT '上级科室系编码',
	dept_level INTEGER COMMENT '科室层级：1 科室系 / 2 临床科室',
	doctor_cnt INTEGER COMMENT '在岗医师数',
	nurse_cnt INTEGER COMMENT '在岗护士数',
	staff_total INTEGER COMMENT '卫生技术人员合计（医师 + 护士）',
	stat_ym VARCHAR(7) COMMENT '台账年月 YYYY-MM',
	etl_batch_date DATE NOT NULL COMMENT '批次业务日期',
	etl_batch_id VARCHAR(32) NOT NULL COMMENT '批次标识 B+yyyyMMdd',
	etl_load_time DATETIME NOT NULL COMMENT '入库时间',
	PRIMARY KEY (dept_code, stat_date),
	KEY idx_dwd_hr_batch (etl_batch_date),
	KEY idx_dwd_hr_stat (stat_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
