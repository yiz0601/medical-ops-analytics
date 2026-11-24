-- =============================================================================
-- 医疗运营数据主题分析平台 —— 容器首次启动的数据库初始化总入口
-- 说明：MySQL 官方镜像只执行 /docker-entrypoint-initdb.d 顶层的 *.sql，
--       因此本文件通过 SOURCE 依次加载各分层脚本（子目录脚本不会自动执行）。
-- 挂载：docker-compose.yml 把项目 sql/ 目录挂到 /docker-entrypoint-initdb.d（只读）
-- 顺序：sys → dim（维表 + 初始化数据）→ ods → dwd → dws → ads
-- =============================================================================

-- 0) 系统表（数据质量告警站内信，质检产出告警后写入）
SOURCE /docker-entrypoint-initdb.d/sys/sys_tables.sql;

-- 1) 公共维表与字典初始化（含科室/病种/费别/号别/DRG 与日期维）
SOURCE /docker-entrypoint-initdb.d/dim/dim_tables.sql;

-- 2) ODS 贴源层
SOURCE /docker-entrypoint-initdb.d/ods/ods_tables.sql;

-- 3) DWD 明细层
SOURCE /docker-entrypoint-initdb.d/dwd/dwd_tables.sql;

-- 4) DWS 汇总层
SOURCE /docker-entrypoint-initdb.d/dws/dws_tables.sql;

-- 5) ADS 集市层
SOURCE /docker-entrypoint-initdb.d/ads/ads_tables.sql;

-- 6) 查询优化索引（幂等）
SOURCE /docker-entrypoint-initdb.d/optimize/optimize_indexes.sql;

-- 7) 初始账号（管理员/分析师/科室用户，bcrypt 哈希）
SOURCE /docker-entrypoint-initdb.d/dim/init_dict.sql;

-- 完成提示
SELECT '数据库初始化完成：sys + dim/ods/dwd/dws/ads 五层 + 索引 + 初始账号' AS init_result;
