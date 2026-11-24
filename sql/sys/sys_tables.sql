-- =============================================================================
-- 医疗运营数据主题分析平台 —— 系统表建表脚本（质量告警站内信通道）
-- 本文件由 backend/etl/jobs/export_ddl.py 自动生成，请勿手工编辑。
-- 来源：backend/etl/config/alert_schema.py
-- 数据库：MySQL 8.0    字符集：utf8mb4    引擎：InnoDB
-- 执行：mysql -h127.0.0.1 -uroot -p < sql/sys/sys_tables.sql
-- =============================================================================

CREATE DATABASE IF NOT EXISTS medical_ops
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_general_ci;

USE medical_ops;

-- 说明：ETL 质检产出告警后写入本表（channel=站内信），记录生成时间与送达时间；
--       通知及时率 = 送达耗时 ≤ 300 秒的告警数 / 告警总数（任务书建设目标 6）

-- ---------------------------------------------------------------- sys_alert
CREATE TABLE IF NOT EXISTS sys_alert (
	id INTEGER NOT NULL AUTO_INCREMENT,
	alert_no VARCHAR(48) NOT NULL COMMENT '告警编号',
	batch_date DATE NOT NULL COMMENT '批次业务日期',
	rule_code VARCHAR(32) NOT NULL COMMENT '规则编号',
	rule_name VARCHAR(64) COMMENT '规则名称',
	table_name VARCHAR(96) COMMENT '校验对象表',
	level VARCHAR(16) COMMENT '告警级别 BLOCK / WARN',
	rule_status VARCHAR(16) COMMENT '规则结果 PASS / WARN / FAIL',
	failed_rows INTEGER COMMENT '异常/失败行数',
	detail TEXT COMMENT '告警明细',
	channel VARCHAR(32) COMMENT '通知通道',
	receive_role VARCHAR(64) COMMENT '接收角色',
	created_at DATETIME NOT NULL COMMENT '告警生成时间',
	notified_at DATETIME COMMENT '送达时间',
	notify_ms INTEGER COMMENT '送达耗时（毫秒）',
	is_read INTEGER COMMENT '是否已读：0 未读 / 1 已读',
	PRIMARY KEY (id),
	UNIQUE (alert_no),
	KEY idx_alert_batch (batch_date),
	KEY idx_alert_read (is_read)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
