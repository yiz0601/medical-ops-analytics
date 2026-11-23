-- =============================================================================
-- 医疗运营数据主题分析平台 —— ODS 层结构与数据校验脚本（阶段二 · 步骤 1-4）
-- 用法：mysql -h127.0.0.1 -uroot -p medical_ops < sql/ods/verify_ods.sql
-- 判定：四段校验全部符合预期即视为"6 张 ODS 表存在且字段完整、行数与基线一致"
-- =============================================================================

USE medical_ops;

-- ---------------------------------------------------------------- 校验 1：表存在性
-- 预期：返回 6 行（ods_his_outpatient_visit / ods_his_inpatient_visit / ods_his_charge_detail
--                    / ods_emr_record / ods_lis_report / ods_finance_excel）
SELECT '校验1·表存在性' AS check_item, table_name, table_rows, table_comment
FROM information_schema.tables
WHERE table_schema = 'medical_ops'
  AND table_name IN (
    'ods_his_outpatient_visit', 'ods_his_inpatient_visit', 'ods_his_charge_detail',
    'ods_emr_record', 'ods_lis_report', 'ods_finance_excel'
  )
ORDER BY table_name;

-- ---------------------------------------------------------------- 校验 2：字段完整性
-- 预期：每张表都包含 etl_batch_date / etl_batch_id / etl_load_time 三个元数据字段
SELECT '校验2·元数据字段' AS check_item, table_name,
       SUM(column_name = 'etl_batch_date') AS has_batch_date,
       SUM(column_name = 'etl_batch_id')   AS has_batch_id,
       SUM(column_name = 'etl_load_time')  AS has_load_time,
       COUNT(*)                            AS column_cnt
FROM information_schema.columns
WHERE table_schema = 'medical_ops'
  AND table_name LIKE 'ods\_%'
GROUP BY table_name
ORDER BY table_name;

-- ---------------------------------------------------------------- 校验 3：行数核对基线
-- 预期：9000 / 1500 / 44078 / 1500 / 2934 / 910，且 diff 列全为 0
SELECT '校验3·行数核对' AS check_item, t.table_name, t.actual_rows, b.expected_rows,
       t.actual_rows - b.expected_rows AS diff,
       IF(t.actual_rows = b.expected_rows, 'OK', 'FAIL') AS result
FROM (
  SELECT 'ods_his_outpatient_visit' AS table_name, COUNT(*) AS actual_rows FROM ods_his_outpatient_visit
  UNION ALL SELECT 'ods_his_inpatient_visit', COUNT(*) FROM ods_his_inpatient_visit
  UNION ALL SELECT 'ods_his_charge_detail',   COUNT(*) FROM ods_his_charge_detail
  UNION ALL SELECT 'ods_emr_record',          COUNT(*) FROM ods_emr_record
  UNION ALL SELECT 'ods_lis_report',          COUNT(*) FROM ods_lis_report
  UNION ALL SELECT 'ods_finance_excel',       COUNT(*) FROM ods_finance_excel
) t
JOIN (
  SELECT 'ods_his_outpatient_visit' AS table_name, 9000 AS expected_rows
  UNION ALL SELECT 'ods_his_inpatient_visit', 1500
  UNION ALL SELECT 'ods_his_charge_detail',   44078
  UNION ALL SELECT 'ods_emr_record',          1500
  UNION ALL SELECT 'ods_lis_report',          2934
  UNION ALL SELECT 'ods_finance_excel',       910
) b ON b.table_name = t.table_name
ORDER BY t.table_name;

-- ---------------------------------------------------------------- 校验 4：批次分布
-- 预期：同一批次日期下各表行数等于基线（重跑不产生重复数据）
SELECT '校验4·批次分布' AS check_item, etl_batch_date, etl_batch_id,
       COUNT(*) AS rows_in_batch
FROM (
  SELECT etl_batch_date, etl_batch_id FROM ods_his_outpatient_visit
  UNION ALL SELECT etl_batch_date, etl_batch_id FROM ods_his_inpatient_visit
  UNION ALL SELECT etl_batch_date, etl_batch_id FROM ods_his_charge_detail
  UNION ALL SELECT etl_batch_date, etl_batch_id FROM ods_emr_record
  UNION ALL SELECT etl_batch_date, etl_batch_id FROM ods_lis_report
  UNION ALL SELECT etl_batch_date, etl_batch_id FROM ods_finance_excel
) u
GROUP BY etl_batch_date, etl_batch_id
ORDER BY etl_batch_date;

-- ---------------------------------------------------------------- 附加检查：主键唯一性
-- 预期：各表 dup_rows = 0
SELECT '附加·主键唯一' AS check_item, 'ods_his_outpatient_visit' AS table_name,
       COUNT(*) - COUNT(DISTINCT visit_id) AS dup_rows FROM ods_his_outpatient_visit
UNION ALL SELECT '附加·主键唯一', 'ods_his_inpatient_visit', COUNT(*) - COUNT(DISTINCT visit_id) FROM ods_his_inpatient_visit
UNION ALL SELECT '附加·主键唯一', 'ods_his_charge_detail',   COUNT(*) - COUNT(DISTINCT charge_id) FROM ods_his_charge_detail
UNION ALL SELECT '附加·主键唯一', 'ods_emr_record',          COUNT(*) - COUNT(DISTINCT record_id) FROM ods_emr_record
UNION ALL SELECT '附加·主键唯一', 'ods_lis_report',          COUNT(*) - COUNT(DISTINCT report_id) FROM ods_lis_report
UNION ALL SELECT '附加·主键唯一', 'ods_finance_excel',       COUNT(*) - COUNT(DISTINCT record_id) FROM ods_finance_excel;

-- ---------------------------------------------------------------- 附加检查：关键字段空值
-- 预期：各计数为 0
SELECT '附加·关键字段空值' AS check_item,
       SUM(visit_id IS NULL OR dept_code IS NULL OR visit_date IS NULL)        AS op_null,
       SUM(visit_type NOT IN ('普通','专家','急诊'))                            AS op_bad_visit_type
FROM ods_his_outpatient_visit;

SELECT '附加·住院字段空值' AS check_item,
       SUM(visit_id IS NULL OR admit_date IS NULL OR discharge_date IS NULL)   AS ip_null,
       SUM(stay_days < 0)                                                      AS ip_bad_stay_days,
       SUM(drug_fee > total_fee)                                               AS ip_fee_inversion
FROM ods_his_inpatient_visit;

SELECT '附加·费别值域' AS check_item,
       COUNT(DISTINCT fee_type_code) AS fee_type_cnt,
       SUM(amount <= 0)              AS bad_amount
FROM ods_his_charge_detail;

-- ---------------------------------------------------------------- 附加检查：业务日期范围
-- 预期：min_date = 2025-04-01，max_date = 2025-06-30
SELECT '附加·日期范围' AS check_item, 'ods_his_outpatient_visit' AS table_name,
       MIN(visit_date) AS min_date, MAX(visit_date) AS max_date FROM ods_his_outpatient_visit
UNION ALL SELECT '附加·日期范围', 'ods_his_charge_detail', MIN(fee_date), MAX(fee_date) FROM ods_his_charge_detail
UNION ALL SELECT '附加·日期范围', 'ods_lis_report', MIN(report_date), MAX(report_date) FROM ods_lis_report
UNION ALL SELECT '附加·日期范围', 'ods_finance_excel', MIN(stat_date), MAX(stat_date) FROM ods_finance_excel;
