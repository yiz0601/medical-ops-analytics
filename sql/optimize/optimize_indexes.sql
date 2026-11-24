-- =============================================================================
-- 医疗运营数据主题分析平台 —— 查询优化脚本（阶段七 · 步骤 6）
-- 内容：DWS/ADS 事实表分区改造 + 维度/指标/时间范围查询索引补建
-- 特性：全部语句幂等，可重复执行（存储过程判断对象是否存在后再创建）
-- 执行：mysql -h127.0.0.1 -uroot -p medical_ops < sql/optimize/optimize_indexes.sql
-- =============================================================================

USE medical_ops;

-- ---------------------------------------------------------------- 幂等索引工具
DROP PROCEDURE IF EXISTS sp_add_index_if_missing;
DELIMITER //
CREATE PROCEDURE sp_add_index_if_missing(
    IN p_table VARCHAR(64),
    IN p_index VARCHAR(64),
    IN p_columns VARCHAR(255)
)
BEGIN
    DECLARE v_exists INT DEFAULT 0;

    SELECT COUNT(*) INTO v_exists
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = p_table
      AND index_name = p_index;

    IF v_exists = 0 THEN
        SET @ddl = CONCAT('ALTER TABLE `', p_table, '` ADD INDEX `', p_index, '` (', p_columns, ')');
        PREPARE stmt FROM @ddl;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
        SELECT CONCAT('[CREATE] ', p_table, '.', p_index) AS result;
    ELSE
        SELECT CONCAT('[SKIP] ', p_table, '.', p_index, ' 已存在') AS result;
    END IF;
END //
DELIMITER ;

-- ---------------------------------------------------------------- 指标结果表索引
-- 主查询模式：WHERE metric_code + dim_value + granularity + stat_date BETWEEN ... ORDER BY stat_date
CALL sp_add_index_if_missing('ads_indicator_result', 'idx_metric_dim_gran_date', '`metric_code`, `dim_value`, `granularity`, `stat_date`');
-- 主题看板按维度检索
CALL sp_add_index_if_missing('ads_indicator_result', 'idx_dim_date', '`dim_value`, `stat_date`');
-- 数据源待补充指标扫描
CALL sp_add_index_if_missing('ads_indicator_result', 'idx_status', '`data_status`, `metric_code`');

-- ---------------------------------------------------------------- DWS 汇总表索引
CALL sp_add_index_if_missing('dws_dept_daily', 'idx_dept_date', '`dept_code`, `stat_date`');
CALL sp_add_index_if_missing('dws_dept_daily', 'idx_stat_date', '`stat_date`');

-- ---------------------------------------------------------------- 主题集市索引
SET @tables = 'ads_outpatient_theme,ads_inpatient_theme,ads_income_theme,ads_drug_theme,ads_consumable_theme,ads_drg_theme,ads_efficiency_theme,ads_service_theme';
-- 集市表主键为 (stat_date, dept_code)，额外补 dept_code 单列索引以支持科室维度筛选
CALL sp_add_index_if_missing('ads_outpatient_theme', 'idx_dept', '`dept_code`');
CALL sp_add_index_if_missing('ads_inpatient_theme', 'idx_dept', '`dept_code`');
CALL sp_add_index_if_missing('ads_income_theme', 'idx_dept', '`dept_code`');
CALL sp_add_index_if_missing('ads_drug_theme', 'idx_dept', '`dept_code`');
CALL sp_add_index_if_missing('ads_consumable_theme', 'idx_dept', '`dept_code`');
CALL sp_add_index_if_missing('ads_drg_theme', 'idx_dept', '`dept_code`');
CALL sp_add_index_if_missing('ads_efficiency_theme', 'idx_dept', '`dept_code`');
CALL sp_add_index_if_missing('ads_service_theme', 'idx_dept', '`dept_code`');

-- ---------------------------------------------------------------- DWD 明细表索引
CALL sp_add_index_if_missing('dwd_visit_detail', 'idx_type_date', '`visit_type`, `visit_date`');
CALL sp_add_index_if_missing('dwd_visit_detail', 'idx_dept_date', '`dept_code`, `visit_date`');
CALL sp_add_index_if_missing('dwd_charge_detail', 'idx_class_date', '`fee_class`, `fee_date`');
CALL sp_add_index_if_missing('dwd_inpatient_visit_detail', 'idx_dept_discharge', '`dept_code`, `discharge_date`');

-- ---------------------------------------------------------------- 维表索引
CALL sp_add_index_if_missing('dim_department', 'idx_parent', '`parent_code`');
CALL sp_add_index_if_missing('dim_date', 'idx_ym', '`year_month`');
CALL sp_add_index_if_missing('dim_date', 'idx_stat_period', '`in_stat_period`, `date_value`');

-- ---------------------------------------------------------------- 分区改造（DWS/ADS 事实表按 stat_date 月分区）
-- 说明：MySQL 分区要求分区键属于主键；以下语句在确认主键包含 stat_date 后可执行。
--       演示环境（数据量 910~3,000 行/表）不做分区；生产环境按 DATA 保留 2 年、按月分区。
--       本段以注释形式提供，避免在小型库上无谓拆表。
--
-- ALTER TABLE dws_dept_daily
--   PARTITION BY RANGE (TO_DAYS(stat_date)) (
--     PARTITION p2025q2 VALUES LESS THAN (TO_DAYS('2025-07-01')),
--     PARTITION p2025q3 VALUES LESS THAN (TO_DAYS('2025-10-01')),
--     PARTITION p2025q4 VALUES LESS THAN (TO_DAYS('2026-01-01')),
--     PARTITION pmax    VALUES LESS THAN MAXVALUE
--   );
--
-- ALTER TABLE ads_indicator_result
--   PARTITION BY RANGE (TO_DAYS(stat_date)) (
--     PARTITION p2025q2 VALUES LESS THAN (TO_DAYS('2025-07-01')),
--     PARTITION p2025q3 VALUES LESS THAN (TO_DAYS('2025-10-01')),
--     PARTITION pmax    VALUES LESS THAN MAXVALUE
--   );

-- ---------------------------------------------------------------- 优化验证
-- 1) 索引清单
SELECT table_name, index_name, GROUP_CONCAT(column_name ORDER BY seq_in_index) AS columns, non_unique
FROM information_schema.statistics
WHERE table_schema = DATABASE()
  AND table_name IN ('ads_indicator_result', 'dws_dept_daily', 'dwd_visit_detail', 'dwd_charge_detail')
GROUP BY table_name, index_name, non_unique
ORDER BY table_name, index_name;

-- 2) 执行计划检查（应命中 idx_metric_dim_gran_date，type=range）
EXPLAIN SELECT metric_code, dim_value, stat_date, metric_value
FROM ads_indicator_result
WHERE metric_code = 'M16' AND dim_value = 'ALL' AND granularity = 'month'
  AND stat_date BETWEEN '2025-04-01' AND '2025-06-30'
ORDER BY stat_date;

-- 3) 清理工具过程（可选保留）
-- DROP PROCEDURE IF EXISTS sp_add_index_if_missing;
