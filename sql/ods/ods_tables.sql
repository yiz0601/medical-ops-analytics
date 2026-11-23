-- =============================================================================
-- 医疗运营数据主题分析平台 —— ODS 贴源层建表脚本（阶段二 · 步骤 1）
-- 数据库：MySQL 8.0    字符集：utf8mb4    引擎：InnoDB
-- 说明：字段与 data/ 下 6 个源 CSV 一一对应，仅追加 3 个 ETL 元数据字段：
--         etl_batch_date  批次业务日期（幂等装载的删除条件）
--         etl_batch_id    批次标识 B+yyyyMMdd（批次追溯）
--         etl_load_time   入库时间
-- 执行：mysql -h127.0.0.1 -uroot -p < sql/ods/ods_tables.sql
-- =============================================================================

CREATE DATABASE IF NOT EXISTS medical_ops
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_general_ci;

USE medical_ops;

-- ---------------------------------------------------------------- 1. HIS 门诊就诊
CREATE TABLE IF NOT EXISTS ods_his_outpatient_visit (
  visit_id        VARCHAR(32)    NOT NULL COMMENT '就诊号',
  patient_id      VARCHAR(32)    DEFAULT NULL COMMENT '患者ID',
  patient_name    VARCHAR(64)    DEFAULT NULL COMMENT '患者姓名（敏感，DWD 层脱敏）',
  id_card         VARCHAR(32)    DEFAULT NULL COMMENT '身份证号（敏感）',
  phone           VARCHAR(32)    DEFAULT NULL COMMENT '联系电话（敏感）',
  gender          VARCHAR(8)     DEFAULT NULL COMMENT '性别',
  age             INT            DEFAULT NULL COMMENT '年龄',
  dept_code       VARCHAR(16)    DEFAULT NULL COMMENT '科室编码',
  visit_date      DATE           DEFAULT NULL COMMENT '就诊日期',
  visit_type      VARCHAR(16)    DEFAULT NULL COMMENT '号别：普通/专家/急诊',
  fee_amount      DECIMAL(12,2)  DEFAULT NULL COMMENT '就诊费用（登记口径）',
  etl_batch_date  DATE           NOT NULL COMMENT '批次业务日期（幂等删除键）',
  etl_batch_id    VARCHAR(32)    NOT NULL COMMENT '批次标识 B+yyyyMMdd',
  etl_load_time   DATETIME       NOT NULL COMMENT '入库时间',
  PRIMARY KEY (visit_id),
  KEY idx_ods_op_visit_date (visit_date),
  KEY idx_ods_op_dept (dept_code),
  KEY idx_ods_op_batch (etl_batch_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ODS·HIS 门诊就诊表（9,000 行基线）';

-- ---------------------------------------------------------------- 2. HIS 住院就诊
CREATE TABLE IF NOT EXISTS ods_his_inpatient_visit (
  visit_id        VARCHAR(32)    NOT NULL COMMENT '住院号',
  patient_id      VARCHAR(32)    DEFAULT NULL COMMENT '患者ID',
  patient_name    VARCHAR(64)    DEFAULT NULL COMMENT '患者姓名（敏感）',
  id_card         VARCHAR(32)    DEFAULT NULL COMMENT '身份证号（敏感）',
  phone           VARCHAR(32)    DEFAULT NULL COMMENT '联系电话（敏感）',
  gender          VARCHAR(8)     DEFAULT NULL COMMENT '性别',
  age             INT            DEFAULT NULL COMMENT '年龄',
  dept_code       VARCHAR(16)    DEFAULT NULL COMMENT '科室编码',
  bed_no          VARCHAR(16)    DEFAULT NULL COMMENT '床位号',
  admit_date      DATE           DEFAULT NULL COMMENT '入院日期',
  discharge_date  DATE           DEFAULT NULL COMMENT '出院日期',
  stay_days       INT            DEFAULT NULL COMMENT '住院天数',
  total_fee       DECIMAL(12,2)  DEFAULT NULL COMMENT '住院总费用（登记口径）',
  drug_fee        DECIMAL(12,2)  DEFAULT NULL COMMENT '药品费用',
  consumable_fee  DECIMAL(12,2)  DEFAULT NULL COMMENT '耗材费用',
  disease_code    VARCHAR(16)    DEFAULT NULL COMMENT 'ICD-10 主诊断编码',
  etl_batch_date  DATE           NOT NULL COMMENT '批次业务日期',
  etl_batch_id    VARCHAR(32)    NOT NULL COMMENT '批次标识',
  etl_load_time   DATETIME       NOT NULL COMMENT '入库时间',
  PRIMARY KEY (visit_id),
  KEY idx_ods_ip_admit_date (admit_date),
  KEY idx_ods_ip_discharge_date (discharge_date),
  KEY idx_ods_ip_dept (dept_code),
  KEY idx_ods_ip_batch (etl_batch_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ODS·HIS 住院就诊表（1,500 行基线）';

-- ---------------------------------------------------------------- 3. HIS 收费明细
CREATE TABLE IF NOT EXISTS ods_his_charge_detail (
  charge_id       VARCHAR(32)    NOT NULL COMMENT '收费流水号',
  visit_id        VARCHAR(32)    DEFAULT NULL COMMENT '就诊号',
  patient_id      VARCHAR(32)    DEFAULT NULL COMMENT '患者ID',
  visit_type      VARCHAR(16)    DEFAULT NULL COMMENT '就诊类型：门诊/住院',
  dept_code       VARCHAR(16)    DEFAULT NULL COMMENT '科室编码',
  fee_date        DATE           DEFAULT NULL COMMENT '收费日期',
  fee_type_code   VARCHAR(16)    DEFAULT NULL COMMENT '费别编码',
  fee_type_name   VARCHAR(32)    DEFAULT NULL COMMENT '费别名称',
  amount          DECIMAL(12,2)  DEFAULT NULL COMMENT '金额',
  etl_batch_date  DATE           NOT NULL COMMENT '批次业务日期',
  etl_batch_id    VARCHAR(32)    NOT NULL COMMENT '批次标识',
  etl_load_time   DATETIME       NOT NULL COMMENT '入库时间',
  PRIMARY KEY (charge_id),
  KEY idx_ods_chg_fee_date (fee_date),
  KEY idx_ods_chg_visit (visit_id),
  KEY idx_ods_chg_dept (dept_code),
  KEY idx_ods_chg_batch (etl_batch_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ODS·HIS 收费明细表（44,078 行基线）';

-- ---------------------------------------------------------------- 4. EMR 病历
CREATE TABLE IF NOT EXISTS ods_emr_record (
  record_id       VARCHAR(32)    NOT NULL COMMENT '病历记录号',
  patient_id      VARCHAR(32)    DEFAULT NULL COMMENT '患者ID',
  visit_id        VARCHAR(32)    DEFAULT NULL COMMENT '就诊号',
  dept_code       VARCHAR(16)    DEFAULT NULL COMMENT '科室编码',
  visit_date      DATE           DEFAULT NULL COMMENT '就诊日期',
  diagnosis       VARCHAR(255)   DEFAULT NULL COMMENT '诊断描述',
  disease_code    VARCHAR(16)    DEFAULT NULL COMMENT 'ICD-10 主诊断编码',
  etl_batch_date  DATE           NOT NULL COMMENT '批次业务日期',
  etl_batch_id    VARCHAR(32)    NOT NULL COMMENT '批次标识',
  etl_load_time   DATETIME       NOT NULL COMMENT '入库时间',
  PRIMARY KEY (record_id),
  KEY idx_ods_emr_visit (visit_id),
  KEY idx_ods_emr_batch (etl_batch_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ODS·EMR 病历表（1,500 行基线）';

-- ---------------------------------------------------------------- 5. LIS 检验
CREATE TABLE IF NOT EXISTS ods_lis_report (
  report_id       VARCHAR(32)    NOT NULL COMMENT '检验报告号',
  patient_id      VARCHAR(32)    DEFAULT NULL COMMENT '患者ID',
  visit_id        VARCHAR(32)    DEFAULT NULL COMMENT '就诊号',
  item_name       VARCHAR(64)    DEFAULT NULL COMMENT '检验项目',
  result_text     VARCHAR(32)    DEFAULT NULL COMMENT '检验结果描述',
  report_date     DATE           DEFAULT NULL COMMENT '报告日期',
  etl_batch_date  DATE           NOT NULL COMMENT '批次业务日期',
  etl_batch_id    VARCHAR(32)    NOT NULL COMMENT '批次标识',
  etl_load_time   DATETIME       NOT NULL COMMENT '入库时间',
  PRIMARY KEY (report_id),
  KEY idx_ods_lis_visit (visit_id),
  KEY idx_ods_lis_batch (etl_batch_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ODS·LIS 检验报告表（2,934 行基线）';

-- ---------------------------------------------------------------- 6. 财务日报（文件通道）
CREATE TABLE IF NOT EXISTS ods_finance_excel (
  record_id            VARCHAR(32)    NOT NULL COMMENT '记录号',
  stat_date            DATE           DEFAULT NULL COMMENT '统计日期',
  dept_code            VARCHAR(16)    DEFAULT NULL COMMENT '科室编码',
  revenue              DECIMAL(14,2)  DEFAULT NULL COMMENT '科室收入',
  drug_revenue         DECIMAL(14,2)  DEFAULT NULL COMMENT '药品收入',
  consumable_revenue   DECIMAL(14,2)  DEFAULT NULL COMMENT '耗材收入',
  etl_batch_date       DATE           NOT NULL COMMENT '批次业务日期',
  etl_batch_id         VARCHAR(32)    NOT NULL COMMENT '批次标识',
  etl_load_time        DATETIME       NOT NULL COMMENT '入库时间',
  PRIMARY KEY (record_id),
  KEY idx_ods_fin_stat_date (stat_date),
  KEY idx_ods_fin_dept (dept_code),
  KEY idx_ods_fin_batch (etl_batch_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ODS·财务日报表（910 行 = 10 科室 × 91 天）';

-- =============================================================================
-- 表清单速查
--   ods_his_outpatient_visit  HIS 门诊就诊      9,000 行
--   ods_his_inpatient_visit   HIS 住院就诊      1,500 行
--   ods_his_charge_detail     HIS 收费明细     44,078 行
--   ods_emr_record            EMR 病历          1,500 行
--   ods_lis_report            LIS 检验报告      2,934 行
--   ods_finance_excel         财务日报            910 行
-- =============================================================================
