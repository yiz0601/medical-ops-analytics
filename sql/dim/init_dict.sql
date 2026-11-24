-- =============================================================================
-- 医疗运营数据主题分析平台 —— 字典与初始账号初始化（阶段七 · 步骤 3）
-- 内容：科室/病种/费别/号别/DRG 字典 + 初始管理员与演示账号（sys_user）
-- 特性：全部 INSERT ... ON DUPLICATE KEY UPDATE，幂等可重跑
-- 说明：字典数据与 backend/etl/config/dim_seed.py 保持一致；dim_tables.sql 已含完整
--       维表 DDL + 初始化，本脚本用于「仅补字典与账号」的运维场景。
-- 执行：mysql -h127.0.0.1 -uroot -p medical_ops < sql/dim/init_dict.sql
-- =============================================================================

USE medical_ops;

-- ---------------------------------------------------------------- 科室字典（10 个临床科室 + 4 个科室系）
INSERT INTO dim_department (dept_code, dept_name, parent_code, dept_level, dept_type, org_area, bed_cnt, doctor_cnt, nurse_cnt, is_active)
VALUES
  ('NK',  '内科系',     NULL, 1, '科室系',   '本部',  0,  0,  0, 1),
  ('WK',  '外科系',     NULL, 1, '科室系',   '本部',  0,  0,  0, 1),
  ('MZ',  '门急诊系',   NULL, 1, '科室系',   '本部',  0,  0,  0, 1),
  ('QT',  '其他科室',   NULL, 1, '科室系',   '本部',  0,  0,  0, 1),
  ('HN',  '呼吸内科',   'NK', 2, '临床科室', '本部', 18, 12, 20, 1),
  ('HX',  '消化内科',   'NK', 2, '临床科室', '本部', 17, 11, 19, 1),
  ('SJ',  '神经内科',   'NK', 2, '临床科室', '本部', 18, 12, 20, 1),
  ('XH',  '心血管内科', 'NK', 2, '临床科室', '本部', 18, 13, 21, 1),
  ('GK',  '骨科',       'WK', 2, '临床科室', '本部', 18, 12, 20, 1),
  ('PW',  '普外科',     'WK', 2, '临床科室', '本部', 18, 12, 20, 1),
  ('FC',  '妇产科',     'WK', 2, '临床科室', '本部', 16, 11, 22, 1),
  ('JZ',  '急诊科',     'MZ', 2, '临床科室', '本部', 18, 14, 24, 1),
  ('EK',  '儿科',       'MZ', 2, '临床科室', '本部', 18, 12, 21, 1),
  ('ICU', '重症医学科', 'QT', 2, '临床科室', '本部', 18, 14, 30, 1)
ON DUPLICATE KEY UPDATE
  dept_name = VALUES(dept_name), parent_code = VALUES(parent_code), dept_level = VALUES(dept_level),
  dept_type = VALUES(dept_type), org_area = VALUES(org_area), bed_cnt = VALUES(bed_cnt),
  doctor_cnt = VALUES(doctor_cnt), nurse_cnt = VALUES(nurse_cnt), is_active = VALUES(is_active);

-- ---------------------------------------------------------------- 病种字典（10 个 ICD-10 主诊断 + 模拟 DRG/DIP 分组）
INSERT INTO dim_disease (disease_code, disease_name, disease_category, drg_code, drg_name, rw, dip_group)
VALUES
  ('I10', '原发性高血压',     '循环系统疾病',     'FM19', '高血压',             0.62, 'DIP-I10'),
  ('I25', '慢性缺血性心脏病', '循环系统疾病',     'FM29', '慢性缺血性心脏病',   0.95, 'DIP-I25'),
  ('I63', '脑梗死',           '神经系统疾病',     'BR29', '脑梗死',             1.35, 'DIP-I63'),
  ('J18', '肺炎',             '呼吸系统疾病',     'ES35', '肺炎',               0.88, 'DIP-J18'),
  ('J44', '慢阻肺',           '呼吸系统疾病',     'EX13', '慢性阻塞性肺疾病',   1.02, 'DIP-J44'),
  ('A09', '感染性腹泻',       '消化系统疾病',     'GK13', '感染性腹泻',         0.55, 'DIP-A09'),
  ('K35', '急性阑尾炎',       '消化系统疾病',     'GD19', '急性阑尾炎',         0.78, 'DIP-K35'),
  ('C16', '胃癌',             '肿瘤',             'GR19', '胃恶性肿瘤',         2.85, 'DIP-C16'),
  ('E11', '糖尿病',           '内分泌与代谢疾病', 'KS19', '2 型糖尿病',         0.72, 'DIP-E11'),
  ('N18', '慢性肾脏病',       '泌尿系统疾病',     'LS35', '慢性肾脏病',         1.18, 'DIP-N18')
ON DUPLICATE KEY UPDATE
  disease_name = VALUES(disease_name), disease_category = VALUES(disease_category),
  drg_code = VALUES(drg_code), drg_name = VALUES(drg_name), rw = VALUES(rw), dip_group = VALUES(dip_group);

-- ---------------------------------------------------------------- 收费类别字典（10 类）
INSERT INTO dim_fee_type (fee_type_code, fee_type_name, fee_class, is_drug, is_consumable, sort_no)
VALUES
  ('GH', '挂号费',   '医疗服务性收入', 0, 0, 1),
  ('JC', '检查费',   '检查检验收入',   0, 0, 2),
  ('JY', '检验费',   '检查检验收入',   0, 0, 3),
  ('ZL', '治疗费',   '医疗服务性收入', 0, 0, 4),
  ('SS', '手术费',   '医疗服务性收入', 0, 0, 5),
  ('CW', '床位费',   '医疗服务性收入', 0, 0, 6),
  ('HL', '护理费',   '医疗服务性收入', 0, 0, 7),
  ('XY', '西药费',   '药品收入',       1, 0, 8),
  ('ZC', '中成药费', '药品收入',       1, 0, 9),
  ('CL', '材料费',   '耗材收入',       0, 1, 10)
ON DUPLICATE KEY UPDATE
  fee_type_name = VALUES(fee_type_name), fee_class = VALUES(fee_class),
  is_drug = VALUES(is_drug), is_consumable = VALUES(is_consumable), sort_no = VALUES(sort_no);

-- ---------------------------------------------------------------- 号别字典（5 类）
INSERT INTO dim_visit_type (visit_type_code, visit_type_name, visit_category)
VALUES
  ('PT',  '普通', '门诊'),
  ('ZJ',  '专家', '门诊'),
  ('JZ',  '急诊', '门急诊'),
  ('OPD', '门诊', '门急诊'),
  ('IPD', '住院', '住院')
ON DUPLICATE KEY UPDATE
  visit_type_name = VALUES(visit_type_name), visit_category = VALUES(visit_category);

-- ---------------------------------------------------------------- 初始账号（bcrypt 哈希，与《部署运维手册》一致）
-- 安全要求：首次登录后立即修改密码；生产环境请用 POST /api/auth/users 新建账号并停用演示账号。
INSERT INTO sys_user (username, password_hash, real_name, role_code, dept_code, is_active)
VALUES
  ('admin',     '$2b$12$PgulLJ7G4A7c6T7A/aoHsOTc1p9UTl7m.rmuSC16vnU9xp0BjdB.u', '系统管理员',   'ADMIN',     NULL, 1),
  ('analyst01', '$2b$12$2tdA0kEbC98WlE3Rkad8o.pXi70/MSkQ8rtTNdHCwqqbkvh8dD7Ya', '运营分析师',   'ANALYST',   NULL, 1),
  ('dept_hn',   '$2b$12$wGxhPpVsMS.h0thRHeWc1O2Khml.n.CuocOdRfr0w.tTPyPLb9CVK', '呼吸内科用户', 'DEPT_USER', 'HN', 1)
ON DUPLICATE KEY UPDATE
  real_name = VALUES(real_name), role_code = VALUES(role_code),
  dept_code = VALUES(dept_code), is_active = VALUES(is_active);

-- ---------------------------------------------------------------- 校验
SELECT '科室字典' AS dict_name, COUNT(*) AS rows_cnt, SUM(bed_cnt) AS total_beds FROM dim_department
UNION ALL SELECT '病种字典', COUNT(*), NULL FROM dim_disease
UNION ALL SELECT '收费类别', COUNT(*), NULL FROM dim_fee_type
UNION ALL SELECT '号别字典', COUNT(*), NULL FROM dim_visit_type
UNION ALL SELECT 'DRG 分组', COUNT(*), NULL FROM dim_drg_group
UNION ALL SELECT '系统账号', COUNT(*), NULL FROM sys_user;
