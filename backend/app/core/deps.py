"""鉴权依赖与数据隔离（阶段四 · 步骤 2.3）。

    get_current_user()             从请求头解析令牌并加载当前用户（含启用校验）
    require_role(*roles)           角色校验依赖工厂，越权返回 403
    apply_data_scope(stmt, user)   科室用户自动追加本科室过滤条件（行级数据权限）
    get_client_ip(request)         取客户端 IP（审计用）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import Select, or_
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.security import decode_token, normalize_role

bearer_scheme = HTTPBearer(auto_error=False, description="Bearer <JWT>")


@dataclass(frozen=True)
class CurrentUser:
    """当前登录用户（令牌 + 数据库校验后的结果）。"""

    user_id: int | None
    username: str
    role: str
    dept_code: str | None
    real_name: str = ""

    @property
    def is_admin(self) -> bool:
        return self.role == "ADMIN"

    @property
    def is_dept_scoped(self) -> bool:
        """科室用户：只能看本科室数据。"""
        return self.role == "DEPT_USER" and bool(self.dept_code)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.user_id,
            "username": self.username,
            "real_name": self.real_name,
            "role_code": self.role,
            "dept_code": self.dept_code,
        }


def get_client_ip(request: Request) -> str:
    """获取客户端 IP（优先 X-Forwarded-For 首个地址）。"""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_session),
) -> CurrentUser:
    """解析 Bearer 令牌 -> 校验 -> 加载用户（停用或不存在返回 401）。"""
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少访问令牌，请先登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(credentials.credentials)
    from app.models.sys import SysUser

    user = (
        session.query(SysUser)
        .filter(SysUser.username == payload.get("sub"))
        .one_or_none()
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已被删除")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="用户已被停用")

    # 令牌中的角色/科室以数据库为准，避免篡改
    return CurrentUser(
        user_id=user.id,
        username=user.username,
        role=normalize_role(user.role_code),
        dept_code=user.dept_code,
        real_name=user.real_name or "",
    )


def require_role(*roles: str):
    """角色校验依赖工厂：`Depends(require_role("ADMIN"))`。"""
    allowed = {normalize_role(role) for role in roles}

    def _dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"角色不足：需要 {'/'.join(sorted(allowed))}，当前 {user.role}",
            )
        return user

    return _dependency


def apply_data_scope(stmt: Select, user: CurrentUser, column_name: str = "dim_value") -> Select:
    """按用户数据权限给查询追加过滤条件。

    * 管理员 / 运营分析师：全院可见（ALL + 各科室）
    * 科室用户：仅本科室（自动排除 ALL 汇总行）
    """
    table = stmt.get_final_froms()[0]
    column = table.c[column_name] if column_name in table.c else None
    if column is None:
        return stmt
    if user.is_dept_scoped:
        return stmt.where(or_(column == user.dept_code, column == user.dept_code))
    return stmt


def assert_dept_allowed(user: CurrentUser, dept_code: str | None) -> None:
    """显式校验科室是否在用户可见范围内（越权抛 403/40302）。"""
    if not user.is_dept_scoped:
        return
    if dept_code and dept_code not in {user.dept_code, "ALL"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="数据越权：超出可见科室范围")
    if dept_code == "ALL":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="数据越权：科室用户不可查看全院汇总")
