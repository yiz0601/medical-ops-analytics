-- =============================================================================
-- 医疗运营数据主题分析平台 —— DWS 汇总层建表脚本（阶段三 · DWS 步骤 1）
-- 本文件由 backend/etl/jobs/export_ddl.py 自动生成，请勿手工编辑。
-- 来源：backend/etl/config/mart_schema.py
-- 数据库：MySQL 8.0    字符集：utf8mb4    引擎：InnoDB
-- 执行：mysql -h127.0.0.1 -uroot -p < sql/dws/dws_tables.sql
-- =============================================================================

CREATE DATABASE IF NOT EXISTS medical_ops
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_general_ci;

USE medical_ops;

-- 说明：主键（科室码 + 日期）唯一，度量字段覆盖门诊/住院/收入/检验/手术/财务口径

-- ---------------------------------------------------------------- dws_dept_daily
CREATE TABLE IF NOT EXISTS dws_dept_daily (
	stat_date DATE NOT NULL COMMENT '统计日期',
	dept_code VARCHAR(16) NOT NULL COMMENT '科室编码',
	dept_name VARCHAR(64) COMMENT '科室名称',
	stat_ym VARCHAR(7) COMMENT '统计年月',
	bed_cnt INTEGER DEFAULT '0' COMMENT '开放床位数（维表快照）',
	op_visit_cnt INTEGER DEFAULT '0' COMMENT '门诊人次',
	op_normal_cnt INTEGER DEFAULT '0' COMMENT '普通号人次',
	op_expert_cnt INTEGER DEFAULT '0' COMMENT '专家号人次',
	op_emergency_cnt INTEGER DEFAULT '0' COMMENT '急诊号人次',
	op_fee_sum NUMERIC(14, 2) DEFAULT '0' COMMENT '门诊费用（登记口径）',
	op_patient_cnt INTEGER DEFAULT '0' COMMENT '门诊患者数（去重）',
	op_repeat_cnt INTEGER DEFAULT '0' COMMENT '复诊人次',
	ip_admit_cnt INTEGER DEFAULT '0' COMMENT '入院人次',
	ip_discharge_cnt INTEGER DEFAULT '0' COMMENT '出院人次',
	bed_days INTEGER DEFAULT '0' COMMENT '实际占用床日数',
	ip_fee_sum NUMERIC(14, 2) DEFAULT '0' COMMENT '住院费用（登记口径）',
	ip_drug_fee_sum NUMERIC(14, 2) DEFAULT '0' COMMENT '住院药品费（登记口径）',
	ip_consumable_fee_sum NUMERIC(14, 2) DEFAULT '0' COMMENT '住院耗材费（登记口径）',
	charge_amt_sum NUMERIC(14, 2) DEFAULT '0' COMMENT '收费合计',
	charge_drug_amt NUMERIC(14, 2) DEFAULT '0' COMMENT '药品收入',
	charge_consumable_amt NUMERIC(14, 2) DEFAULT '0' COMMENT '耗材收入',
	charge_exam_lab_amt NUMERIC(14, 2) DEFAULT '0' COMMENT '检查检验收入',
	charge_service_amt NUMERIC(14, 2) DEFAULT '0' COMMENT '医疗服务性收入',
	op_charge_amt NUMERIC(14, 2) DEFAULT '0' COMMENT '门诊收入（流水）',
	ip_charge_amt NUMERIC(14, 2) DEFAULT '0' COMMENT '住院收入（流水）',
	lis_report_cnt INTEGER DEFAULT '0' COMMENT '检验报告数',
	lis_abnormal_cnt INTEGER DEFAULT '0' COMMENT '检验异常报告数',
	ip_ss_visit_cnt INTEGER DEFAULT '0' COMMENT '含手术费的住院就诊数',
	fin_revenue NUMERIC(14, 2) DEFAULT '0' COMMENT '财务口径收入',
	fin_drug_revenue NUMERIC(14, 2) DEFAULT '0' COMMENT '财务口径药品收入',
	fin_consumable_revenue NUMERIC(14, 2) DEFAULT '0' COMMENT '财务口径耗材收入',
	drg_cases INTEGER DEFAULT '0' COMMENT 'DRG 入组病例数',
	drg_rw_sum NUMERIC(14, 2) DEFAULT '0' COMMENT 'DRG 权重合计',
	etl_batch_date DATE COMMENT '批次业务日期',
	etl_load_time DATETIME COMMENT '入库时间',
	PRIMARY KEY (stat_date, dept_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
