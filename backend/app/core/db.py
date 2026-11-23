"""数据库引擎与会话依赖（阶段四）。

- `get_engine()`       进程内缓存引擎，连接串来自 Settings
- `get_session()`      FastAPI 依赖，逐请求创建 Session（测试可用 dependency_overrides 替换）
- `ensure_schema()`    建表并初始化默认账号（幂等）
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """获取（缓存的）数据库引擎。"""
    settings = get_settings()
    url = settings.resolved_db_url()
    connect_args: dict[str, object] = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(url, echo=settings.db_echo, future=True, pool_pre_ping=True, connect_args=connect_args)


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    """获取 Session 工厂。"""
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


def get_session() -> Iterator[Session]:
    """FastAPI 依赖：逐请求提供数据库会话。"""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def ensure_schema(engine: Engine | None = None) -> list[str]:
    """建表（幂等）并写入默认账号，返回已创建的表名列表。"""
    from app.models.sys import Base, seed_default_users

    eng = engine or get_engine()
    Base.metadata.create_all(eng, checkfirst=True)
    with sessionmaker(bind=eng, expire_on_commit=False, future=True)() as session:
        seed_default_users(session)
    return sorted(Base.metadata.tables)


def reset_engine_cache() -> None:
    """清空引擎与工厂缓存（测试或切换连接串后调用）。"""
    get_engine.cache_clear()
    get_session_factory.cache_clear()
