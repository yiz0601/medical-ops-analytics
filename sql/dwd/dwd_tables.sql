-- =============================================================================
-- 医疗运营数据主题分析平台 —— DWD 明细层建表脚本（阶段二 · 步骤 3-1）
-- 数据库：MySQL 8.0    字符集：utf8mb4    引擎：InnoDB
-- 说明：ODS 经去重、填充、编码标准化、隐私脱敏后写入本层；1 业务事件 1 行。
--       隐私字段一律以 *_masked 形式存储，原值仅保留在 ODS（仅 DBA/ETL 账号可读）。
-- 执行：mysql -h127.0.0.1 -uroot -p medical_ops < sql/dwd/dwd_tables.sql
-- =============================================================================

USE medical_ops;

-- ---------------------------------------------------------------- 1. 门诊就诊明细
CREATE TABLE IF NOT EXISTS dwd_outpatient_visit_detail (
  visit_id             VARCHAR(32)    NOT NULL COMMENT '就诊号',
  patient_id           VARCHAR(32)    DEFAULT NULL COMMENT '患者ID',
  patient_name_masked  VARCHAR(64)    DEFAULT NULL COMMENT '姓名（脱敏）',
  id_card_masked       VARCHAR(32)    DEFAULT NULL COMMENT '身份证号（脱敏）',
  phone_masked         VARCHAR(32)    DEFAULT NULL COMMENT '手机号（脱敏）',
  gender               VARCHAR(8)     DEFAULT NULL COMMENT '性别',
  age                  INT            DEFAULT NULL COMMENT '年龄',
  age_group            VARCHAR(16)    DEFAULT NULL COMMENT '年龄段：儿童/青年/中年/老年',
  dept_code            VARCHAR(16)    DEFAULT NULL COMMENT '科室编码',
  dept_name            VARCHAR(64)    DEFAULT NULL COMMENT '科室名称',
  visit_date           DATE           DEFAULT NULL COMMENT '就诊日期',
  visit_ym             VARCHAR(7)     DEFAULT NULL COMMENT '就诊年月 YYYY-MM',
  visit_type           VARCHAR(16)    DEFAULT NULL COMMENT '号别',
  visit_type_code      VARCHAR(8)     DEFAULT NULL COMMENT '号别编码 PT/ZJ/JZ',
  fee_amount           DECIMAL(12,2)  DEFAULT NULL COMMENT '就诊费用（登记口径）',
  etl_batch_date       DATE           NOT NULL COMMENT '批次业务日期',
  etl_batch_id         VARCHAR(32)    NOT NULL COMMENT '批次标识',
  etl_load_time        DATETIME       NOT NULL COMMENT '入库时间',
  PRIMARY KEY (visit_id),
  KEY idx_dwd_op_date (visit_date),
  KEY idx_dwd_op_dept (dept_code),
  KEY idx_dwd_op_patient (patient_id),
  KEY idx_dwd_op_batch (etl_batch_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='DWD·门诊就诊明细（9,000 行基线）';

-- ---------------------------------------------------------------- 2. 住院就诊明细
CREATE TABLE IF NOT EXISTS dwd_inpatient_visit_detail (
  visit_id             VARCHAR(32)    NOT NULL COMMENT '住院号',
  patient_id           VARCHAR(32)    DEFAULT NULL COMMENT '患者ID',
  patient_name_masked  VARCHAR(64)    DEFAULT NULL COMMENT '姓名（脱敏）',
  id_card_masked       VARCHAR(32)    DEFAULT NULL COMMENT '身份证号（脱敏）',
  phone_masked         VARCHAR(32)    DEFAULT NULL COMMENT '手机号（脱敏）',
  gender               VARCHAR(8)     DEFAULT NULL COMMENT '性别',
  age                  INT            DEFAULT NULL COMMENT '年龄',
  age_group            VARCHAR(16)    DEFAULT NULL COMMENT '年龄段',
  dept_code            VARCHAR(16)    DEFAULT NULL COMMENT '科室编码',
  dept_name            VARCHAR(64)    DEFAULT NULL COMMENT '科室名称',
  bed_no               VARCHAR(16)    DEFAULT NULL COMMENT '床位号',
  admit_date           DATE           DEFAULT NULL COMMENT '入院日期',
  discharge_date       DATE           DEFAULT NULL COMMENT '出院日期',
  stay_days            INT            DEFAULT NULL COMMENT '住院天数',
  total_fee            DECIMAL(12,2)  DEFAULT NULL COMMENT '住院总费用（登记口径）',
  drug_fee             DECIMAL(12,2)  DEFAULT NULL COMMENT '药品费用',
  consumable_fee       DECIMAL(12,2)  DEFAULT NULL COMMENT '耗材费用',
  disease_code         VARCHAR(16)    DEFAULT NULL COMMENT 'ICD-10 主诊断编码',
  disease_name         VARCHAR(64)    DEFAULT NULL COMMENT '病种名称',
  drg_code             VARCHAR(16)    DEFAULT NULL COMMENT 'DRG 组编码（模拟分组）',
  rw                   DECIMAL(6,2)   DEFAULT NULL COMMENT 'DRG 权重 RW',
  etl_batch_date       DATE           NOT NULL COMMENT '批次业务日期',
  etl_batch_id         VARCHAR(32)    NOT NULL COMMENT '批次标识',
  etl_load_time        DATETIME       NOT NULL COMMENT '入库时间',
  PRIMARY KEY (visit_id),
  KEY idx_dwd_ip_admit (admit_date),
  KEY idx_dwd_ip_discharge (discharge_date),
  KEY idx_dwd_ip_dept (dept_code),
  KEY idx_dwd_ip_disease (disease_code),
  KEY idx_dwd_ip_batch (etl_batch_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='DWD·住院就诊明细（1,500 行基线）';

-- ---------------------------------------------------------------- 3. 收费明细
CREATE TABLE IF NOT EXISTS dwd_charge_detail (
  charge_id        VARCHAR(32)    NOT NULL COMMENT '收费流水号',
  visit_id         VARCHAR(32)    DEFAULT NULL COMMENT '就诊号',
  patient_id       VARCHAR(32)    DEFAULT NULL COMMENT '患者ID',
  visit_type       VARCHAR(16)    DEFAULT NULL COMMENT '就诊类型：门诊/住院',
  visit_type_code  VARCHAR(8)     DEFAULT NULL COMMENT '就诊类型编码 OPD/IPD',
  dept_code        VARCHAR(16)    DEFAULT NULL COMMENT '科室编码',
  dept_name        VARCHAR(64)    DEFAULT NULL COMMENT '科室名称',
  fee_date         DATE           DEFAULT NULL COMMENT '收费日期',
  fee_ym           VARCHAR(7)     DEFAULT NULL COMMENT '收费年月 YYYY-MM',
  fee_type_code    VARCHAR(16)    DEFAULT NULL COMMENT '费别编码',
  fee_type_name    VARCHAR(32)    DEFAULT NULL COMMENT '费别名称',
  fee_class        VARCHAR(32)    DEFAULT NULL COMMENT '费别归类：药品/耗材/检查检验/医疗服务性',
  amount           DECIMAL(12,2)  DEFAULT NULL COMMENT '金额',
  etl_batch_date   DATE           NOT NULL COMMENT '批次业务日期',
  etl_batch_id     VARCHAR(32)    NOT NULL COMMENT '批次标识',
  etl_load_time    DATETIME       NOT NULL COMMENT '入库时间',
  PRIMARY KEY (charge_id),
  KEY idx_dwd_chg_date (fee_date),
  KEY idx_dwd_chg_visit (visit_id),
  KEY idx_dwd_chg_dept (dept_code),
  KEY idx_dwd_chg_class (fee_class),
  KEY idx_dwd_chg_batch (etl_batch_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='DWD·收费明细（44,078 行基线）';

-- ---------------------------------------------------------------- 4. 病历明细
CREATE TABLE IF NOT EXISTS dwd_emr_record_detail (
  record_id        VARCHAR(32)    NOT NULL COMMENT '病历记录号',
  patient_id       VARCHAR(32)    DEFAULT NULL COMMENT '患者ID',
  visit_id         VARCHAR(32)    DEFAULT NULL COMMENT '就诊号',
  dept_code        VARCHAR(16)    DEFAULT NULL COMMENT '科室编码',
  dept_name        VARCHAR(64)    DEFAULT NULL COMMENT '科室名称',
  visit_date       DATE           DEFAULT NULL COMMENT '就诊日期',
  diagnosis        VARCHAR(255)   DEFAULT NULL COMMENT '诊断描述',
  disease_code     VARCHAR(16)    DEFAULT NULL COMMENT 'ICD-10 编码',
  disease_name     VARCHAR(64)    DEFAULT NULL COMMENT '病种名称',
  drg_code         VARCHAR(16)    DEFAULT NULL COMMENT 'DRG 组编码（模拟分组）',
  etl_batch_date   DATE           NOT NULL COMMENT '批次业务日期',
  etl_batch_id     VARCHAR(32)    NOT NULL COMMENT '批次标识',
  etl_load_time    DATETIME       NOT NULL COMMENT '入库时间',
  PRIMARY KEY (record_id),
  KEY idx_dwd_emr_visit (visit_id),
  KEY idx_dwd_emr_disease (disease_code),
  KEY idx_dwd_emr_batch (etl_batch_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='DWD·病历明细（1,500 行基线）';

-- ---------------------------------------------------------------- 5. 检验明细
CREATE TABLE IF NOT EXISTS dwd_lis_report_detail (
  report_id        VARCHAR(32)    NOT NULL COMMENT '检验报告号',
  patient_id       VARCHAR(32)    DEFAULT NULL COMMENT '患者ID',
  visit_id         VARCHAR(32)    DEFAULT NULL COMMENT '就诊号',
  item_name        VARCHAR(64)    DEFAULT NULL COMMENT '检验项目',
  result_text      VARCHAR(32)    DEFAULT NULL COMMENT '检验结果描述',
  result_flag      VARCHAR(16)    DEFAULT NULL COMMENT '结果判定：正常/异常',
  report_date      DATE           DEFAULT NULL COMMENT '报告日期',
  etl_batch_date   DATE           NOT NULL COMMENT '批次业务日期',
  etl_batch_id     VARCHAR(32)    NOT NULL COMMENT '批次标识',
  etl_load_time    DATETIME       NOT NULL COMMENT '入库时间',
  PRIMARY KEY (report_id),
  KEY idx_dwd_lis_visit (visit_id),
  KEY idx_dwd_lis_flag (result_flag),
  KEY idx_dwd_lis_batch (etl_batch_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='DWD·检验明细（2,934 行基线）';

-- ---------------------------------------------------------------- 6. 财务日报明细（扩展表）
CREATE TABLE IF NOT EXISTS dwd_finance_daily_detail (
  record_id            VARCHAR(32)    NOT NULL COMMENT '记录号',
  stat_date            DATE           DEFAULT NULL COMMENT '统计日期',
  stat_ym              VARCHAR(7)     DEFAULT NULL COMMENT '统计年月 YYYY-MM',
  dept_code            VARCHAR(16)    DEFAULT NULL COMMENT '科室编码',
  dept_name            VARCHAR(64)    DEFAULT NULL COMMENT '科室名称',
  revenue              DECIMAL(14,2)  DEFAULT NULL COMMENT '科室收入',
  drug_revenue         DECIMAL(14,2)  DEFAULT NULL COMMENT '药品收入',
  consumable_revenue   DECIMAL(14,2)  DEFAULT NULL COMMENT '耗材收入',
  etl_batch_date       DATE           NOT NULL COMMENT '批次业务日期',
  etl_batch_id         VARCHAR(32)    NOT NULL COMMENT '批次标识',
  etl_load_time        DATETIME       NOT NULL COMMENT '入库时间',
  PRIMARY KEY (record_id),
  KEY idx_dwd_fin_date (stat_date),
  KEY idx_dwd_fin_dept (dept_code),
  KEY idx_dwd_fin_batch (etl_batch_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='DWD·财务日报明细（910 行基线）';

-- ---------------------------------------------------------------- DWD 校验
-- 行数对账：预期与 ODS 一致（9000/1500/44078/1500/2934/910）
SELECT 'DWD 行数对账' AS check_item, t.table_name, t.rows_cnt,
       IF(t.rows_cnt = b.expected_rows, 'OK', 'FAIL') AS result
FROM (
  SELECT 'dwd_outpatient_visit_detail' AS table_name, COUNT(*) AS rows_cnt FROM dwd_outpatient_visit_detail
  UNION ALL SELECT 'dwd_inpatient_visit_detail', COUNT(*) FROM dwd_inpatient_visit_detail
  UNION ALL SELECT 'dwd_charge_detail',          COUNT(*) FROM dwd_charge_detail
  UNION ALL SELECT 'dwd_emr_record_detail',      COUNT(*) FROM dwd_emr_record_detail
  UNION ALL SELECT 'dwd_lis_report_detail',      COUNT(*) FROM dwd_lis_report_detail
  UNION ALL SELECT 'dwd_finance_daily_detail',   COUNT(*) FROM dwd_finance_daily_detail
) t
JOIN (
  SELECT 'dwd_outpatient_visit_detail' AS table_name, 9000 AS expected_rows
  UNION ALL SELECT 'dwd_inpatient_visit_detail', 1500
  UNION ALL SELECT 'dwd_charge_detail',          44078
  UNION ALL SELECT 'dwd_emr_record_detail',      1500
  UNION ALL SELECT 'dwd_lis_report_detail',      2934
  UNION ALL SELECT 'dwd_finance_daily_detail',   910
) b ON b.table_name = t.table_name
ORDER BY t.table_name;

-- 脱敏校验：预期 masked_ok = 总行数（不残留明文姓名/身份证/手机号）
SELECT 'DWD 脱敏校验' AS check_item,
       COUNT(*) AS total_rows,
       SUM(patient_name_masked LIKE '%*%') AS masked_name_rows,
       SUM(id_card_masked LIKE '%*%')      AS masked_id_rows,
       SUM(phone_masked LIKE '%*%')        AS masked_phone_rows
FROM dwd_outpatient_visit_detail;

-- 编码标准化校验：费别归类分布（预期仅 4 类，无 UNKNOWN）
SELECT 'DWD 费别归类' AS check_item, fee_class, COUNT(*) AS rows_cnt, SUM(amount) AS amount_sum
FROM dwd_charge_detail
GROUP BY fee_class
ORDER BY rows_cnt DESC;
