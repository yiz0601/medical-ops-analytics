"""认证接口（阶段四 · 步骤 2.2）。

    POST /api/auth/login    校验密码并返回 JWT 与用户信息
    POST /api/auth/users    新建用户（仅管理员），密码入库前 bcrypt 哈希
    GET  /api/auth/profile  返回当前登录用户信息

JWT 密钥与有效期（jwt_expire_minutes，默认 480）来自 Settings，支持环境变量覆盖。
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
from app.core.deps import CurrentUser, get_client_ip, get_current_user, require_role
from app.core.response import BusinessError, ok
from app.core.security import create_access_token, hash_password, normalize_role, verify_password
from app.models.sys import SysUser, get_user_by_username
from app.schemas.auth import LoginIn, TokenOut, UserCreateIn, UserOut
from app.schemas.common import ApiResponse, ErrorResponse
from app.services.audit_service import log_action

router = APIRouter(prefix="/auth", tags=["认证鉴权"])

ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "参数校验失败"},
    401: {"model": ErrorResponse, "description": "用户名或密码错误 / 令牌失效"},
    403: {"model": ErrorResponse, "description": "角色不足"},
    409: {"model": ErrorResponse, "description": "账号已存在"},
}


def _to_user_out(user: SysUser) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        real_name=user.real_name or "",
        role_code=normalize_role(user.role_code),
        dept_code=user.dept_code,
    )


@router.post(
    "/login",
    response_model=ApiResponse[TokenOut],
    summary="用户登录",
    description="校验用户名与密码，成功返回 JWT 访问令牌与用户信息；失败返回 401。",
    responses=ERROR_RESPONSES,
)
def login(
    payload: LoginIn,
    request: Request,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict:
    """登录并签发令牌。"""
    settings = get_settings()
    user = get_user_by_username(session, payload.username)
    client_ip = get_client_ip(request)

    if user is None or not verify_password(payload.password, user.password_hash):
        log_action(
            background,
            user=None,
            action="login",
            resource="/api/auth/login",
            detail=f"username={payload.username}",
            result="FAIL",
            client_ip=client_ip,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="用户已被停用")

    token = create_access_token(user)
    current = CurrentUser(
        user_id=user.id,
        username=user.username,
        role=normalize_role(user.role_code),
        dept_code=user.dept_code,
        real_name=user.real_name or "",
    )
    log_action(
        background,
        user=current,
        action="login",
        resource="/api/auth/login",
        detail=f"role={current.role} dept={current.dept_code or '-'}",
        client_ip=client_ip,
    )
    return ok(
        TokenOut(
            access_token=token,
            token_type="bearer",
            expires_in=settings.jwt_expire_minutes * 60,
            user=_to_user_out(user),
        )
    )


@router.post(
    "/users",
    response_model=ApiResponse[UserOut],
    status_code=status.HTTP_201_CREATED,
    summary="新建用户（仅管理员）",
    description="仅 ADMIN 角色可调用；密码入库前使用 bcrypt 哈希，账号重复返回 409。",
    responses=ERROR_RESPONSES,
)
def create_user(
    payload: UserCreateIn,
    request: Request,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
    current: CurrentUser = Depends(require_role("ADMIN")),
) -> dict:
    """创建用户。"""
    if get_user_by_username(session, payload.username) is not None:
        raise BusinessError(40901, f"账号已存在：{payload.username}", status_code=status.HTTP_409_CONFLICT)

    role = normalize_role(payload.role_code)
    if role not in {"ADMIN", "ANALYST", "DEPT_USER"}:
        raise BusinessError(40001, f"非法角色：{payload.role_code}")
    if role == "DEPT_USER" and not payload.dept_code:
        raise BusinessError(40001, "科室用户必须指定 dept_code")

    user = SysUser(
        username=payload.username,
        password_hash=hash_password(payload.password),
        real_name=payload.real_name or "",
        role_code=role,
        dept_code=payload.dept_code,
        is_active=1,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    log_action(
        background,
        user=current,
        action="create_user",
        resource="/api/auth/users",
        detail=f"username={user.username} role={role} dept={user.dept_code or '-'}",
        client_ip=get_client_ip(request),
    )
    return ok(_to_user_out(user))


@router.get(
    "/profile",
    response_model=ApiResponse[UserOut],
    summary="当前登录用户信息",
    responses={401: ERROR_RESPONSES[401]},
)
def profile(
    session: Session = Depends(get_session),
    current: CurrentUser = Depends(get_current_user),
) -> dict:
    """返回当前用户（含角色与数据范围）。"""
    user = session.execute(select(SysUser).where(SysUser.username == current.username)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    return ok(_to_user_out(user))


@router.get(
    "/users",
    response_model=ApiResponse[list[UserOut]],
    summary="用户列表（仅管理员）",
    responses=ERROR_RESPONSES,
)
def list_users(
    session: Session = Depends(get_session),
    _: CurrentUser = Depends(require_role("ADMIN")),
) -> dict:
    """列出全部用户。"""
    users = session.execute(select(SysUser).order_by(SysUser.id)).scalars().all()
    return ok([_to_user_out(user) for user in users])
