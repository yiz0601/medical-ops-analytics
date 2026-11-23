-- =============================================================================
-- 医疗运营数据主题分析平台 —— 公共维表建表与初始化脚本（阶段三 · 步骤 1）
-- 本文件由 backend/etl/jobs/export_ddl.py 自动生成，请勿手工编辑。
-- 来源：backend/etl/config/dim_schema.py + dim_seed.py
-- 数据库：MySQL 8.0    字符集：utf8mb4    引擎：InnoDB
-- 执行：mysql -h127.0.0.1 -uroot -p < sql/dim/dim_tables.sql
-- =============================================================================

CREATE DATABASE IF NOT EXISTS medical_ops
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_general_ci;

USE medical_ops;

-- ---------------------------------------------------------------- dim_department
CREATE TABLE IF NOT EXISTS dim_department (
	dept_code VARCHAR(16) NOT NULL COMMENT '科室标准码',
	dept_name VARCHAR(64) NOT NULL COMMENT '科室名称',
	parent_code VARCHAR(16) COMMENT '上级科室系编码',
	dept_level INTEGER NOT NULL DEFAULT '2' COMMENT '层级：1 科室系 / 2 临床科室',
	dept_type VARCHAR(32) COMMENT '科室类型',
	org_area VARCHAR(32) COMMENT '院区（数据权限隔离维度）',
	bed_cnt INTEGER DEFAULT '0' COMMENT '开放床位数',
	doctor_cnt INTEGER DEFAULT '0' COMMENT '医师数',
	nurse_cnt INTEGER DEFAULT '0' COMMENT '护士数',
	is_active INTEGER DEFAULT '1' COMMENT '是否启用',
	PRIMARY KEY (dept_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='科室维表（标准码、名称、层级、院区、床位与人力）';

-- ---------------------------------------------------------------- dim_date
CREATE TABLE IF NOT EXISTS dim_date (
	date_key INTEGER NOT NULL COMMENT '日期键 YYYYMMDD',
	date_value DATE NOT NULL COMMENT '日期值',
	year INTEGER NOT NULL COMMENT '年',
	quarter INTEGER COMMENT '季度',
	month INTEGER COMMENT '月',
	`year_month` VARCHAR(7) COMMENT '年月 YYYY-MM',
	day_of_month INTEGER COMMENT '日',
	week_of_year INTEGER COMMENT '年内第几周（ISO）',
	iso_year INTEGER COMMENT 'ISO 年',
	day_of_week INTEGER COMMENT '星期（1=周一）',
	weekday_name VARCHAR(8) COMMENT '星期名称',
	is_weekend INTEGER COMMENT '是否周末',
	is_holiday INTEGER COMMENT '是否法定节假日',
	holiday_name VARCHAR(32) COMMENT '节假日名称',
	in_stat_period INTEGER COMMENT '是否在数据统计期内',
	PRIMARY KEY (date_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='日期维表（年/季/月/周/星期/周末/节假日）';

-- ---------------------------------------------------------------- dim_disease
CREATE TABLE IF NOT EXISTS dim_disease (
	disease_code VARCHAR(16) NOT NULL COMMENT 'ICD-10 编码',
	disease_name VARCHAR(64) NOT NULL COMMENT '病种名称',
	disease_category VARCHAR(32) COMMENT '疾病大类',
	drg_code VARCHAR(16) COMMENT 'DRG 组编码（模拟分组）',
	drg_name VARCHAR(64) COMMENT 'DRG 组名称',
	rw NUMERIC(6, 2) COMMENT 'DRG 权重 RW',
	dip_group VARCHAR(32) COMMENT 'DIP 病种分值组',
	PRIMARY KEY (disease_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='病种维表（ICD 编码、疾病大类、DRG/DIP 分组与权重）';

-- ---------------------------------------------------------------- dim_fee_type
CREATE TABLE IF NOT EXISTS dim_fee_type (
	fee_type_code VARCHAR(16) NOT NULL COMMENT '收费类别编码',
	fee_type_name VARCHAR(32) NOT NULL COMMENT '收费类别名称',
	fee_class VARCHAR(32) COMMENT '收入归类：药品/耗材/检查检验/医疗服务性',
	is_drug INTEGER DEFAULT '0' COMMENT '是否药品',
	is_consumable INTEGER DEFAULT '0' COMMENT '是否耗材',
	sort_no INTEGER DEFAULT '0' COMMENT '排序号',
	PRIMARY KEY (fee_type_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='收费类别维表（挂号/检查/检验/治疗/手术/床位/护理/药品/耗材）';

-- ---------------------------------------------------------------- dim_drg_group
CREATE TABLE IF NOT EXISTS dim_drg_group (
	drg_code VARCHAR(16) NOT NULL COMMENT 'DRG 组编码',
	drg_name VARCHAR(64) COMMENT 'DRG 组名称',
	disease_code VARCHAR(16) COMMENT '对应 ICD-10 主诊断',
	rw NUMERIC(6, 2) COMMENT '权重 RW',
	PRIMARY KEY (drg_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='DRG 分组维表（扩展：病种 → 组别 → 权重）';

-- ---------------------------------------------------------------- dim_visit_type
CREATE TABLE IF NOT EXISTS dim_visit_type (
	visit_type_code VARCHAR(8) NOT NULL COMMENT '号别编码',
	visit_type_name VARCHAR(16) NOT NULL COMMENT '号别名称',
	visit_category VARCHAR(16) COMMENT '归类：门诊/门急诊/住院',
	PRIMARY KEY (visit_type_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='号别字典（扩展：普通/专家/急诊/门诊/住院）';

-- ================================ 初始化数据 ================================

-- 科室维表：4 个科室系 + 10 个临床科室（开放床位合计 177）
INSERT INTO dim_department (dept_code, dept_name, parent_code, dept_level, dept_type, org_area, bed_cnt, doctor_cnt, nurse_cnt, is_active) VALUES
  ('NK', '内科系', NULL, 1, '科室系', '本部', 0, 0, 0, 1),
  ('WK', '外科系', NULL, 1, '科室系', '本部', 0, 0, 0, 1),
  ('MZ', '门急诊系', NULL, 1, '科室系', '本部', 0, 0, 0, 1),
  ('QT', '其他科室', NULL, 1, '科室系', '本部', 0, 0, 0, 1),
  ('HN', '呼吸内科', 'NK', 2, '临床科室', '本部', 18, 12, 20, 1),
  ('HX', '消化内科', 'NK', 2, '临床科室', '本部', 17, 11, 19, 1),
  ('SJ', '神经内科', 'NK', 2, '临床科室', '本部', 18, 12, 20, 1),
  ('XH', '心血管内科', 'NK', 2, '临床科室', '本部', 18, 13, 21, 1),
  ('GK', '骨科', 'WK', 2, '临床科室', '本部', 18, 12, 20, 1),
  ('PW', '普外科', 'WK', 2, '临床科室', '本部', 18, 12, 20, 1),
  ('FC', '妇产科', 'WK', 2, '临床科室', '本部', 16, 11, 22, 1),
  ('JZ', '急诊科', 'MZ', 2, '临床科室', '本部', 18, 14, 24, 1),
  ('EK', '儿科', 'MZ', 2, '临床科室', '本部', 18, 12, 21, 1),
  ('ICU', '重症医学科', 'QT', 2, '临床科室', '本部', 18, 14, 30, 1)
ON DUPLICATE KEY UPDATE dept_name=VALUES(dept_name), parent_code=VALUES(parent_code), dept_level=VALUES(dept_level), dept_type=VALUES(dept_type), org_area=VALUES(org_area), bed_cnt=VALUES(bed_cnt), doctor_cnt=VALUES(doctor_cnt), nurse_cnt=VALUES(nurse_cnt), is_active=VALUES(is_active);

-- 病种维表：10 个 ICD-10 主诊断（含模拟 DRG 分组与权重）
INSERT INTO dim_disease (disease_code, disease_name, disease_category, drg_code, drg_name, rw, dip_group) VALUES
  ('I10', '原发性高血压', '循环系统疾病', 'FM19', '高血压', 0.62, 'DIP-I10'),
  ('I25', '慢性缺血性心脏病', '循环系统疾病', 'FM29', '慢性缺血性心脏病', 0.95, 'DIP-I25'),
  ('I63', '脑梗死', '神经系统疾病', 'BR29', '脑梗死', 1.35, 'DIP-I63'),
  ('J18', '肺炎', '呼吸系统疾病', 'ES35', '肺炎', 0.88, 'DIP-J18'),
  ('J44', '慢阻肺', '呼吸系统疾病', 'EX13', '慢性阻塞性肺疾病', 1.02, 'DIP-J44'),
  ('A09', '感染性腹泻', '消化系统疾病', 'GK13', '感染性腹泻', 0.55, 'DIP-A09'),
  ('K35', '急性阑尾炎', '消化系统疾病', 'GD19', '急性阑尾炎', 0.78, 'DIP-K35'),
  ('C16', '胃癌', '肿瘤', 'GR19', '胃恶性肿瘤', 2.85, 'DIP-C16'),
  ('E11', '糖尿病', '内分泌与代谢疾病', 'KS19', '2 型糖尿病', 0.72, 'DIP-E11'),
  ('N18', '慢性肾脏病', '泌尿系统疾病', 'LS35', '慢性肾脏病', 1.18, 'DIP-N18')
ON DUPLICATE KEY UPDATE disease_name=VALUES(disease_name), disease_category=VALUES(disease_category), drg_code=VALUES(drg_code), drg_name=VALUES(drg_name), rw=VALUES(rw), dip_group=VALUES(dip_group);

-- DRG 分组维表（扩展）
INSERT INTO dim_drg_group (drg_code, drg_name, disease_code, rw) VALUES
  ('FM19', '高血压', 'I10', 0.62),
  ('FM29', '慢性缺血性心脏病', 'I25', 0.95),
  ('BR29', '脑梗死', 'I63', 1.35),
  ('ES35', '肺炎', 'J18', 0.88),
  ('EX13', '慢性阻塞性肺疾病', 'J44', 1.02),
  ('GK13', '感染性腹泻', 'A09', 0.55),
  ('GD19', '急性阑尾炎', 'K35', 0.78),
  ('GR19', '胃恶性肿瘤', 'C16', 2.85),
  ('KS19', '2 型糖尿病', 'E11', 0.72),
  ('LS35', '慢性肾脏病', 'N18', 1.18)
ON DUPLICATE KEY UPDATE drg_name=VALUES(drg_name), disease_code=VALUES(disease_code), rw=VALUES(rw);

-- 收费类别维表：10 类（含收入归类与药品/耗材标记）
INSERT INTO dim_fee_type (fee_type_code, fee_type_name, fee_class, is_drug, is_consumable, sort_no) VALUES
  ('GH', '挂号费', '医疗服务性收入', 0, 0, 1),
  ('JC', '检查费', '检查检验收入', 0, 0, 2),
  ('JY', '检验费', '检查检验收入', 0, 0, 3),
  ('ZL', '治疗费', '医疗服务性收入', 0, 0, 4),
  ('SS', '手术费', '医疗服务性收入', 0, 0, 5),
  ('CW', '床位费', '医疗服务性收入', 0, 0, 6),
  ('HL', '护理费', '医疗服务性收入', 0, 0, 7),
  ('XY', '西药费', '药品收入', 1, 0, 8),
  ('ZC', '中成药费', '药品收入', 1, 0, 9),
  ('CL', '材料费', '耗材收入', 0, 1, 10)
ON DUPLICATE KEY UPDATE fee_type_name=VALUES(fee_type_name), fee_class=VALUES(fee_class), is_drug=VALUES(is_drug), is_consumable=VALUES(is_consumable), sort_no=VALUES(sort_no);

-- 号别字典（扩展）
INSERT INTO dim_visit_type (visit_type_code, visit_type_name, visit_category) VALUES
  ('PT', '普通', '门诊'),
  ('ZJ', '专家', '门诊'),
  ('JZ', '急诊', '门急诊'),
  ('OPD', '门诊', '门急诊'),
  ('IPD', '住院', '住院')
ON DUPLICATE KEY UPDATE visit_type_name=VALUES(visit_type_name), visit_category=VALUES(visit_category);

-- 日期维表：2024-04-01 ~ 2026-06-30（覆盖数据期 2025-04-01 ~ 2025-06-30 前后各 1 年）
SET SESSION cte_max_recursion_depth = 2000;

INSERT INTO dim_date (date_key, date_value, year, quarter, month, year_month, day_of_month,
                      week_of_year, iso_year, day_of_week, weekday_name, is_weekend,
                      is_holiday, holiday_name, in_stat_period)
WITH RECURSIVE d AS (
  SELECT DATE('2024-04-01') AS dt
  UNION ALL
  SELECT DATE_ADD(dt, INTERVAL 1 DAY) FROM d WHERE dt < DATE('2026-06-30')
)
SELECT CAST(DATE_FORMAT(dt, '%Y%m%d') AS UNSIGNED), dt, YEAR(dt), QUARTER(dt), MONTH(dt),
       DATE_FORMAT(dt, '%Y-%m'), DAY(dt), WEEK(dt, 3), YEARWEEK(dt, 3) DIV 100,
       WEEKDAY(dt) + 1,
       ELT(WEEKDAY(dt) + 1, '周一', '周二', '周三', '周四', '周五', '周六', '周日'),
       IF(WEEKDAY(dt) >= 5, 1, 0), 0, '',
       IF(dt BETWEEN '2025-04-01' AND '2025-06-30', 1, 0)
FROM d
ON DUPLICATE KEY UPDATE date_value = VALUES(date_value);

-- 法定节假日标记（与 backend/etl/config/dim_seed.py 中的 HOLIDAYS 一致）
UPDATE dim_date dd
JOIN (
  SELECT DATE('2024-04-04') AS dt, '清明节' AS nm UNION ALL
  SELECT DATE('2024-04-05') AS dt, '清明节' AS nm UNION ALL
  SELECT DATE('2024-04-06') AS dt, '清明节' AS nm UNION ALL
  SELECT DATE('2024-05-01') AS dt, '劳动节' AS nm UNION ALL
  SELECT DATE('2024-05-02') AS dt, '劳动节' AS nm UNION ALL
  SELECT DATE('2024-05-03') AS dt, '劳动节' AS nm UNION ALL
  SELECT DATE('2024-05-04') AS dt, '劳动节' AS nm UNION ALL
  SELECT DATE('2024-05-05') AS dt, '劳动节' AS nm UNION ALL
  SELECT DATE('2024-06-10') AS dt, '端午节' AS nm UNION ALL
  SELECT DATE('2024-09-15') AS dt, '中秋节' AS nm UNION ALL
  SELECT DATE('2024-09-16') AS dt, '中秋节' AS nm UNION ALL
  SELECT DATE('2024-09-17') AS dt, '中秋节' AS nm UNION ALL
  SELECT DATE('2024-10-01') AS dt, '国庆节' AS nm UNION ALL
  SELECT DATE('2024-10-02') AS dt, '国庆节' AS nm UNION ALL
  SELECT DATE('2024-10-03') AS dt, '国庆节' AS nm UNION ALL
  SELECT DATE('2024-10-04') AS dt, '国庆节' AS nm UNION ALL
  SELECT DATE('2024-10-05') AS dt, '国庆节' AS nm UNION ALL
  SELECT DATE('2024-10-06') AS dt, '国庆节' AS nm UNION ALL
  SELECT DATE('2024-10-07') AS dt, '国庆节' AS nm UNION ALL
  SELECT DATE('2025-01-01') AS dt, '元旦' AS nm UNION ALL
  SELECT DATE('2025-01-28') AS dt, '春节' AS nm UNION ALL
  SELECT DATE('2025-01-29') AS dt, '春节' AS nm UNION ALL
  SELECT DATE('2025-01-30') AS dt, '春节' AS nm UNION ALL
  SELECT DATE('2025-01-31') AS dt, '春节' AS nm UNION ALL
  SELECT DATE('2025-02-01') AS dt, '春节' AS nm UNION ALL
  SELECT DATE('2025-02-02') AS dt, '春节' AS nm UNION ALL
  SELECT DATE('2025-02-03') AS dt, '春节' AS nm UNION ALL
  SELECT DATE('2025-02-04') AS dt, '春节' AS nm UNION ALL
  SELECT DATE('2025-04-04') AS dt, '清明节' AS nm UNION ALL
  SELECT DATE('2025-04-05') AS dt, '清明节' AS nm UNION ALL
  SELECT DATE('2025-04-06') AS dt, '清明节' AS nm UNION ALL
  SELECT DATE('2025-05-01') AS dt, '劳动节' AS nm UNION ALL
  SELECT DATE('2025-05-02') AS dt, '劳动节' AS nm UNION ALL
  SELECT DATE('2025-05-03') AS dt, '劳动节' AS nm UNION ALL
  SELECT DATE('2025-05-04') AS dt, '劳动节' AS nm UNION ALL
  SELECT DATE('2025-05-05') AS dt, '劳动节' AS nm UNION ALL
  SELECT DATE('2025-05-31') AS dt, '端午节' AS nm UNION ALL
  SELECT DATE('2025-06-01') AS dt, '端午节' AS nm UNION ALL
  SELECT DATE('2025-06-02') AS dt, '端午节' AS nm UNION ALL
  SELECT DATE('2025-10-01') AS dt, '国庆节' AS nm UNION ALL
  SELECT DATE('2025-10-02') AS dt, '国庆节' AS nm UNION ALL
  SELECT DATE('2025-10-03') AS dt, '国庆节' AS nm UNION ALL
  SELECT DATE('2025-10-04') AS dt, '国庆节' AS nm UNION ALL
  SELECT DATE('2025-10-05') AS dt, '国庆节' AS nm UNION ALL
  SELECT DATE('2025-10-06') AS dt, '国庆节' AS nm UNION ALL
  SELECT DATE('2025-10-07') AS dt, '国庆节' AS nm UNION ALL
  SELECT DATE('2025-10-08') AS dt, '国庆节' AS nm UNION ALL
  SELECT DATE('2026-01-01') AS dt, '元旦' AS nm UNION ALL
  SELECT DATE('2026-02-16') AS dt, '春节' AS nm UNION ALL
  SELECT DATE('2026-02-17') AS dt, '春节' AS nm UNION ALL
  SELECT DATE('2026-02-18') AS dt, '春节' AS nm UNION ALL
  SELECT DATE('2026-02-19') AS dt, '春节' AS nm UNION ALL
  SELECT DATE('2026-02-20') AS dt, '春节' AS nm UNION ALL
  SELECT DATE('2026-02-21') AS dt, '春节' AS nm UNION ALL
  SELECT DATE('2026-02-22') AS dt, '春节' AS nm UNION ALL
  SELECT DATE('2026-04-04') AS dt, '清明节' AS nm UNION ALL
  SELECT DATE('2026-04-05') AS dt, '清明节' AS nm UNION ALL
  SELECT DATE('2026-04-06') AS dt, '清明节' AS nm UNION ALL
  SELECT DATE('2026-05-01') AS dt, '劳动节' AS nm UNION ALL
  SELECT DATE('2026-05-02') AS dt, '劳动节' AS nm UNION ALL
  SELECT DATE('2026-05-03') AS dt, '劳动节' AS nm UNION ALL
  SELECT DATE('2026-05-04') AS dt, '劳动节' AS nm UNION ALL
  SELECT DATE('2026-05-05') AS dt, '劳动节' AS nm UNION ALL
  SELECT DATE('2026-06-19') AS dt, '端午节' AS nm UNION ALL
  SELECT DATE('2026-06-20') AS dt, '端午节' AS nm UNION ALL
  SELECT DATE('2026-06-21') AS dt, '端午节' AS nm
) h ON h.dt = dd.date_value
SET dd.is_holiday = 1, dd.holiday_name = h.nm;

-- ---------------------------------------------------------------- 维表校验
-- ---------------------------------------------------------------- 行数核对
SELECT t.table_name, t.actual_rows, t.expected_rows,
       IF(t.actual_rows = t.expected_rows, 'OK', 'FAIL') AS result
FROM (
  SELECT 'dim_department' AS table_name, COUNT(*) AS actual_rows, 14 AS expected_rows FROM dim_department
  UNION ALL SELECT 'dim_disease' AS table_name, COUNT(*) AS actual_rows, 10 AS expected_rows FROM dim_disease
  UNION ALL SELECT 'dim_fee_type' AS table_name, COUNT(*) AS actual_rows, 10 AS expected_rows FROM dim_fee_type
  UNION ALL SELECT 'dim_drg_group' AS table_name, COUNT(*) AS actual_rows, 10 AS expected_rows FROM dim_drg_group
  UNION ALL SELECT 'dim_visit_type' AS table_name, COUNT(*) AS actual_rows, 5 AS expected_rows FROM dim_visit_type
  UNION ALL SELECT 'dim_date' AS table_name, COUNT(*) AS actual_rows, 821 AS expected_rows FROM dim_date
) t;

-- 统计期天数（应 91）与开放床位合计（应 177）
SELECT COUNT(*) AS stat_days FROM dim_date WHERE in_stat_period = 1;
SELECT SUM(bed_cnt) AS total_beds FROM dim_department WHERE dept_level = 2;
