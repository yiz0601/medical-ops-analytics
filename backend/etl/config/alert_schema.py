"""数据质量告警表（站内信通知通道）。

ETL 质检产出告警后写入 `sys_alert`，应用侧提供未读计数、告警列表与已读接口，
并据此统计「告警通知及时率」：送达时间 − 生成时间 ≤ `ALERT_TIMELY_SECONDS` 记为及时。

设计要点：
    * 与 ETL 的 ODS/DWD/DWS/ADS 表共存于同一数据库，应用侧与 ETL 侧共用本表定义（单一来源）
    * 幂等：同一批次重跑时按 `batch_date` 先删后插，避免告警重复堆积
    * 通道：站内信（默认）。邮件/IM 通道预留 `channel` 字段，接入新通道不影响既有统计
"""

from __future__ import annotations

from sqlalchemy import Column, Date, DateTime, Index, Integer, MetaData, String, Table, Text
from sqlalchemy.engine import Engine

ALERT_METADATA = MetaData()

# 及时性阈值（秒）：生成到送达的间隔不超过该值即视为及时
ALERT_TIMELY_SECONDS = 300

# 默认通知通道与接收角色
ALERT_CHANNEL = "站内信"
ALERT_RECEIVE_ROLE = "ADMIN,ANALYST"

sys_alert = Table(
    "sys_alert",
    ALERT_METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("alert_no", String(48), nullable=False, unique=True, comment="告警编号"),
    Column("batch_date", Date, nullable=False, comment="批次业务日期"),
    Column("rule_code", String(32), nullable=False, comment="规则编号"),
    Column("rule_name", String(64), comment="规则名称"),
    Column("table_name", String(96), comment="校验对象表"),
    Column("level", String(16), comment="告警级别 BLOCK / WARN"),
    Column("rule_status", String(16), comment="规则结果 PASS / WARN / FAIL"),
    Column("failed_rows", Integer, default=0, comment="异常/失败行数"),
    Column("detail", Text, comment="告警明细"),
    Column("channel", String(32), default=ALERT_CHANNEL, comment="通知通道"),
    Column("receive_role", String(64), default=ALERT_RECEIVE_ROLE, comment="接收角色"),
    Column("created_at", DateTime, nullable=False, comment="告警生成时间"),
    Column("notified_at", DateTime, comment="送达时间"),
    Column("notify_ms", Integer, comment="送达耗时（毫秒）"),
    Column("is_read", Integer, default=0, comment="是否已读：0 未读 / 1 已读"),
    Index("idx_alert_batch", "batch_date"),
    Index("idx_alert_read", "is_read"),
)


def create_alert_tables(engine: Engine) -> None:
    """创建告警表（幂等，表已存在时跳过）。"""
    ALERT_METADATA.create_all(engine)
