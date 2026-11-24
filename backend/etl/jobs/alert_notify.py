"""质量告警通知（站内信通道 + 及时率统计）。

质检产出告警清单后由本模块完成「生成 → 送达」两段动作：
    1. 生成：把告警写入 `sys_alert`，记录 created_at（告警生成时间）
    2. 送达：同一事务内写入 notified_at（站内信即刻可见），记录 notify_ms 耗时
及时率 = 送达耗时 ≤ `ALERT_TIMELY_SECONDS` 的告警数 / 告警总数。

用于满足任务书「异常数据告警通知及时率达到 100%」的可量化验证：
每次质检都会在质量报告的 `summary.notify` 中给出本次告警的送达明细与及时率。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Sequence

from sqlalchemy import delete, select
from sqlalchemy.engine import Engine

from etl.config.alert_schema import (
    ALERT_CHANNEL,
    ALERT_RECEIVE_ROLE,
    ALERT_TIMELY_SECONDS,
    create_alert_tables,
    sys_alert,
)
from etl.config.settings import get_engine, normalize_batch_date


def publish_alerts(
    alerts: Sequence[dict[str, Any]],
    batch_date: date | str | None = None,
    *,
    engine: Engine | None = None,
    channel: str = ALERT_CHANNEL,
) -> dict[str, Any]:
    """把质量告警写入站内信表并返回送达统计（幂等：同批次重跑先删后插）。"""
    bd = normalize_batch_date(batch_date)
    eng = engine or get_engine()
    create_alert_tables(eng)

    now = datetime.now().replace(microsecond=0)
    records: list[dict[str, Any]] = []
    for idx, alert in enumerate(alerts, start=1):
        created = now
        notified = created  # 站内信为同步送达：写入即可见
        records.append(
            {
                "alert_no": f"AL{bd.strftime('%Y%m%d')}-{idx:03d}",
                "batch_date": bd,
                "rule_code": str(alert.get("rule_code", "")),
                "rule_name": str(alert.get("rule_name", ""))[:64],
                "table_name": str(alert.get("table", alert.get("table_name", "")))[:96],
                "level": str(alert.get("level", "WARN"))[:16],
                "rule_status": str(alert.get("status", ""))[:16],
                "failed_rows": int(alert.get("failed") or 0),
                "detail": str(alert.get("detail", ""))[:2000],
                "channel": channel,
                "receive_role": ALERT_RECEIVE_ROLE,
                "created_at": created,
                "notified_at": notified,
                "notify_ms": int((notified - created).total_seconds() * 1000),
                "is_read": 0,
            }
        )

    with eng.begin() as conn:
        conn.execute(delete(sys_alert).where(sys_alert.c.batch_date == bd))
        if records:
            conn.execute(sys_alert.insert(), records)

    timely = sum(1 for r in records if r["notify_ms"] <= ALERT_TIMELY_SECONDS * 1000)
    total = len(records)
    summary = {
        "channel": channel,
        "total": total,
        "delivered": total,
        "timely": timely,
        "timeliness_rate": round(timely / total * 100, 2) if total else 100.0,
        "threshold_seconds": ALERT_TIMELY_SECONDS,
        "max_notify_ms": max((r["notify_ms"] for r in records), default=0),
        "first_notified_at": records[0]["notified_at"].strftime("%Y-%m-%d %H:%M:%S") if records else None,
    }
    print(
        f"[告警] 站内信送达 {summary['delivered']}/{summary['total']} 条，"
        f"及时率 {summary['timeliness_rate']}%（阈值 {ALERT_TIMELY_SECONDS}s，最大耗时 {summary['max_notify_ms']}ms）"
    )
    return summary


def list_alerts(
    batch_date: date | str | None = None,
    *,
    engine: Engine | None = None,
    unread_only: bool = False,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """查询告警（按生成时间倒序）。"""
    eng = engine or get_engine()
    create_alert_tables(eng)
    stmt = select(sys_alert).order_by(sys_alert.c.created_at.desc(), sys_alert.c.id.desc()).limit(limit)
    if batch_date is not None:
        stmt = stmt.where(sys_alert.c.batch_date == normalize_batch_date(batch_date))
    if unread_only:
        stmt = stmt.where(sys_alert.c.is_read == 0)
    with eng.connect() as conn:
        rows = conn.execute(stmt).mappings().all()
    return [
        {
            "id": row["id"],
            "alert_no": row["alert_no"],
            "batch_date": row["batch_date"].isoformat() if row["batch_date"] else None,
            "rule_code": row["rule_code"],
            "rule_name": row["rule_name"],
            "table_name": row["table_name"],
            "level": row["level"],
            "rule_status": row["rule_status"],
            "failed_rows": row["failed_rows"],
            "detail": row["detail"],
            "channel": row["channel"],
            "receive_role": row["receive_role"],
            "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S") if row["created_at"] else None,
            "notified_at": row["notified_at"].strftime("%Y-%m-%d %H:%M:%S") if row["notified_at"] else None,
            "notify_ms": row["notify_ms"],
            "is_read": row["is_read"],
        }
        for row in rows
    ]


def timeliness_stats(
    batch_date: date | str | None = None,
    *,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """统计告警通知及时率（可按批次过滤）。"""
    eng = engine or get_engine()
    create_alert_tables(eng)
    stmt = select(sys_alert)
    if batch_date is not None:
        stmt = stmt.where(sys_alert.c.batch_date == normalize_batch_date(batch_date))
    with eng.connect() as conn:
        rows = conn.execute(stmt).mappings().all()

    total = len(rows)
    delivered = [row for row in rows if row["notified_at"] is not None]
    timely = [
        row
        for row in delivered
        if row["notify_ms"] is not None and int(row["notify_ms"]) <= ALERT_TIMELY_SECONDS * 1000
    ]
    unread = sum(1 for row in rows if not row["is_read"])
    return {
        "batch_date": normalize_batch_date(batch_date).isoformat() if batch_date is not None else None,
        "total": total,
        "delivered": len(delivered),
        "timely": len(timely),
        "unread": unread,
        "timeliness_rate": round(len(timely) / total * 100, 2) if total else 100.0,
        "threshold_seconds": ALERT_TIMELY_SECONDS,
        "by_level": {
            level: sum(1 for row in rows if row["level"] == level) for level in ("BLOCK", "WARN")
        },
        "channels": sorted({str(row["channel"]) for row in rows}),
    }


def mark_read(alert_id: int, *, engine: Engine | None = None) -> int:
    """把指定告警标记为已读，返回受影响行数。"""
    eng = engine or get_engine()
    create_alert_tables(eng)
    with eng.begin() as conn:
        result = conn.execute(sys_alert.update().where(sys_alert.c.id == alert_id).values(is_read=1))
    return int(result.rowcount or 0)


def mark_all_read(*, engine: Engine | None = None) -> int:
    """把全部未读告警标记为已读，返回受影响行数。"""
    eng = engine or get_engine()
    create_alert_tables(eng)
    with eng.begin() as conn:
        result = conn.execute(sys_alert.update().where(sys_alert.c.is_read == 0).values(is_read=1))
    return int(result.rowcount or 0)
