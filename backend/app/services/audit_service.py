"""审计日志服务（阶段四 · 步骤 2.4）。

    write_audit(session, ...)      同步写入审计表（用户、动作、资源、明细、时间、IP、结果）
    log_action(background, ...)    通过 BackgroundTasks 后台写入，避免阻塞主请求
    list_audits(session, ...)      查询最近审计记录（管理员排查用）
"""

from __future__ import annotations

from typing import Any

from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser
from app.models.sys import SysAuditLog


def write_audit(
    session: Session,
    *,
    user: CurrentUser | None,
    action: str,
    resource: str,
    detail: str = "",
    result: str = "OK",
    client_ip: str = "",
) -> SysAuditLog:
    """写入一条审计记录并提交。"""
    record = SysAuditLog(
        user_id=user.user_id if user else None,
        username=user.username if user else "anonymous",
        role_code=user.role if user else "",
        action=action,
        resource=resource,
        detail=detail[:2000],
        result=result,
        client_ip=client_ip,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _write_with_new_session(
    *,
    user: CurrentUser | None,
    action: str,
    resource: str,
    detail: str,
    result: str,
    client_ip: str,
) -> None:
    """使用独立会话写审计（后台任务内不能复用请求会话）。"""
    from app.core.db import get_session_factory

    session = get_session_factory()()
    try:
        write_audit(
            session,
            user=user,
            action=action,
            resource=resource,
            detail=detail,
            result=result,
            client_ip=client_ip,
        )
    except Exception:  # noqa: BLE001 - 审计失败不得影响主流程
        session.rollback()
    finally:
        session.close()


def log_action(
    background: BackgroundTasks | None,
    *,
    user: CurrentUser | None,
    action: str,
    resource: str,
    detail: str = "",
    result: str = "OK",
    client_ip: str = "",
) -> None:
    """记录操作审计。

    传入 `BackgroundTasks` 时后台写入（返回响应后执行），否则降级为同步写入。
    """
    kwargs: dict[str, Any] = {
        "user": user,
        "action": action,
        "resource": resource,
        "detail": detail,
        "result": result,
        "client_ip": client_ip,
    }
    if background is not None:
        background.add_task(_write_with_new_session, **kwargs)
        return
    from app.core.db import get_session_factory

    session = get_session_factory()()
    try:
        write_audit(session, **kwargs)
    finally:
        session.close()


def list_audits(session: Session, limit: int = 50, action: str | None = None) -> list[dict[str, Any]]:
    """查询最近审计记录（按时间倒序）。"""
    stmt = select(SysAuditLog).order_by(SysAuditLog.id.desc()).limit(max(1, min(limit, 500)))
    if action:
        stmt = stmt.where(SysAuditLog.action == action)
    return [row.to_dict() for row in session.execute(stmt).scalars().all()]
