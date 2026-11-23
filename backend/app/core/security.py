"""密码哈希与 JWT 令牌（阶段四 · 步骤 2.1）。

    hash_password(password)           bcrypt 哈希
    verify_password(password, hashed) 校验明文与哈希
    create_access_token(user)         签发 JWT（含 user_id / role / department）
    decode_token(token)               校验解码，过期或伪造抛 401
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from fastapi import HTTPException, status
from jose import JWTError, jwt

from app.core.config import get_settings

# 角色别名：便于外部按 admin / analyst / department 传参
ROLE_ALIASES: dict[str, str] = {
    "admin": "ADMIN",
    "analyst": "ANALYST",
    "department": "DEPT_USER",
    "dept": "DEPT_USER",
    "dept_user": "DEPT_USER",
    "ADMIN": "ADMIN",
    "ANALYST": "ANALYST",
    "DEPT_USER": "DEPT_USER",
}


def normalize_role(role: str | None) -> str:
    """把角色别名规整为标准编码。"""
    if not role:
        return "ANALYST"
    return ROLE_ALIASES.get(str(role), ROLE_ALIASES.get(str(role).lower(), str(role).upper()))


def hash_password(password: str) -> str:
    """生成 bcrypt 哈希（cost 默认 12）。"""
    if not password:
        raise ValueError("密码不能为空")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """校验明文密码与哈希是否匹配（异常一律判为不匹配）。"""
    if not password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(user: Any, expires_minutes: int | None = None) -> str:
    """签发访问令牌。user 可为 ORM 对象或含 username/role_code/dept_code 的字典。"""
    settings = get_settings()
    minutes = int(expires_minutes or settings.jwt_expire_minutes)

    def _pick(obj: Any, *names: str) -> Any:
        for name in names:
            if isinstance(obj, dict):
                if name in obj:
                    return obj[name]
            elif hasattr(obj, name):
                return getattr(obj, name)
        return None

    username = _pick(user, "username")
    user_id = _pick(user, "id", "user_id")
    role = normalize_role(_pick(user, "role_code", "role"))
    department = _pick(user, "dept_code", "department")

    now = datetime.now(tz=timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(username),
        "user_id": user_id,
        "role": role,
        "department": department,
        "iss": settings.jwt_issuer,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    """解码并校验令牌；过期、伪造或格式错误统一抛 401。"""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"令牌无效或已过期：{exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    if not payload.get("sub"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="令牌缺少用户标识")
    return payload
