"""质量告警通知服务（站内信通道）。

应用侧与 ETL 侧共用 `etl.config.alert_schema.sys_alert` 表定义（单一来源）：
* ETL 质检产出告警后写入并记录送达时间（见 `etl.jobs.alert_notify.publish_alerts`）
* 应用侧通过本服务提供未读计数、告警列表、已读标记与通知及时率统计
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from etl.jobs.alert_notify import (
    list_alerts as _list_alerts,
    mark_all_read as _mark_all_read,
    mark_read as _mark_read,
    timeliness_stats as _timeliness_stats,
)


def _engine(session: Session):
    """取会话绑定的引擎（应用与 ETL 共用同一数据库）。"""
    bind = session.get_bind()
    return getattr(bind, "engine", bind)


def list_alerts(
    session: Session,
    *,
    batch_date: str | None = None,
    unread_only: bool = False,
    limit: int = 50,
) -> dict[str, Any]:
    """返回告警列表、未读数与及时率统计。"""
    engine = _engine(session)
    items = _list_alerts(batch_date=batch_date, engine=engine, unread_only=unread_only, limit=limit)
    stats = _timeliness_stats(batch_date=batch_date, engine=engine)
    return {
        "unread": stats.get("unread", 0),
        "items": items,
        "timeliness": stats,
    }


def timeliness(session: Session, batch_date: str | None = None) -> dict[str, Any]:
    """告警通知及时率统计。"""
    return _timeliness_stats(batch_date=batch_date, engine=_engine(session))


def mark_read(session: Session, alert_id: int) -> int:
    """标记单条告警已读。"""
    return _mark_read(alert_id, engine=_engine(session))


def mark_all_read(session: Session) -> int:
    """全部标记已读。"""
    return _mark_all_read(engine=_engine(session))
