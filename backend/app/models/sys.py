"""系统表模型：用户与审计日志（阶段四 · 步骤 2.2 / 2.4）。

    sys_user       用户与角色（ADMIN 管理员 / ANALYST 运营分析师 / DEPT_USER 科室用户）
    sys_audit_log  操作审计（用户、动作、资源、明细、时间、IP、结果）
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    """应用侧 ORM 基类（与 ETL 的 Core 表共存于同一数据库）。"""


class SysUser(Base):
    __tablename__ = "sys_user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, comment="登录账号")
    password_hash: Mapped[str] = mapped_column(String(200), comment="bcrypt 哈希")
    real_name: Mapped[str] = mapped_column(String(64), default="", comment="姓名")
    role_code: Mapped[str] = mapped_column(String(32), default="ANALYST", comment="角色编码")
    dept_code: Mapped[str | None] = mapped_column(String(16), nullable=True, comment="所属科室（数据权限）")
    is_active: Mapped[int] = mapped_column(Integer, default=1, comment="是否启用")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "username": self.username,
            "real_name": self.real_name,
            "role_code": self.role_code,
            "dept_code": self.dept_code,
            "is_active": self.is_active,
        }


class SysAuditLog(Base):
    __tablename__ = "sys_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="操作人 ID")
    username: Mapped[str] = mapped_column(String(64), default="", comment="操作人账号")
    role_code: Mapped[str] = mapped_column(String(32), default="", comment="操作人角色")
    action: Mapped[str] = mapped_column(String(64), comment="动作：login / query / export / trigger ...")
    resource: Mapped[str] = mapped_column(String(128), default="", comment="资源：接口路径或表名")
    detail: Mapped[str] = mapped_column(Text, default="", comment="明细（参数、结果行数等）")
    result: Mapped[str] = mapped_column(String(16), default="OK", comment="结果：OK / FAIL")
    client_ip: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.username,
            "role_code": self.role_code,
            "action": self.action,
            "resource": self.resource,
            "detail": self.detail,
            "result": self.result,
            "client_ip": self.client_ip,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
        }


# 默认账号（与《部署运维手册》《用户操作手册》一致）：admin / analyst01 / dept_hn
DEFAULT_USERS: list[dict[str, object]] = [
    {"username": "admin", "password": "Admin@123", "real_name": "系统管理员", "role_code": "ADMIN", "dept_code": None},
    {"username": "analyst01", "password": "Analyst@123", "real_name": "运营分析师", "role_code": "ANALYST", "dept_code": None},
    {"username": "dept_hn", "password": "Dept@123", "real_name": "呼吸内科用户", "role_code": "DEPT_USER", "dept_code": "HN"},
]


def seed_default_users(session: Session) -> int:
    """初始化默认账号（已存在则跳过），返回新增数量。"""
    from app.core.security import hash_password

    created = 0
    for item in DEFAULT_USERS:
        exists = session.execute(select(SysUser).where(SysUser.username == item["username"])).scalar_one_or_none()
        if exists:
            continue
        session.add(
            SysUser(
                username=str(item["username"]),
                password_hash=hash_password(str(item["password"])),
                real_name=str(item["real_name"]),
                role_code=str(item["role_code"]),
                dept_code=item["dept_code"],  # type: ignore[arg-type]
                is_active=1,
            )
        )
        created += 1
    if created:
        session.commit()
    return created


def get_user_by_username(session: Session, username: str) -> SysUser | None:
    return session.execute(select(SysUser).where(SysUser.username == username)).scalar_one_or_none()
