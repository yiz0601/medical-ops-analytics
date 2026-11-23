"""应用入口与工厂（阶段四 · 步骤 1-1）。

    create_app()   应用工厂：注册 CORS、统一响应包装中间件、全局异常处理与全部路由
    app            模块级实例，供 `uvicorn app.main:app` 使用

启动：
    cd backend
    uvicorn app.main:app --reload --port 8000
接口文档：http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.db import ensure_schema
from app.core.response import EnvelopeMiddleware, register_exception_handlers

logger = logging.getLogger("moa.api")

DESCRIPTION = """
医疗运营数据主题分析平台后端服务：指标查询、多维分析、看板、报表导出与任务监控。

* 统一响应外壳：`{"code": 0, "msg": "success", "data": {...}}`
* 鉴权方式：`Authorization: Bearer <JWT>`（`POST /api/auth/login` 获取）
* 数据权限：科室用户仅可见本科室指标，管理员与运营分析师可见全院
"""


@asynccontextmanager
async def lifespan(_: FastAPI):
    """应用生命周期：启动时建表与初始化默认账号（失败不阻断启动，便于本地无库调试）。"""
    try:
        tables = ensure_schema()
        logger.info("schema ready: %s tables", len(tables))
    except Exception as exc:  # noqa: BLE001 - 启动期数据库不可用不应阻断进程
        logger.warning("ensure_schema skipped: %s", exc)
    yield


def create_app() -> FastAPI:
    """应用工厂：装配中间件、异常处理与路由。"""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description=DESCRIPTION,
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url=f"{settings.api_prefix}/openapi.json",
        lifespan=lifespan,
    )

    # 统一响应外壳（内层）+ CORS（外层）
    app.add_middleware(EnvelopeMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/health", tags=["系统"], summary="健康检查", description="容器健康探针与 Nginx 上游检查。")
    def health() -> dict:
        """返回服务状态与版本（经外壳包装为统一响应）。"""
        return {"status": "up", "version": settings.app_version, "env": settings.app_env}

    @app.get(f"{settings.api_prefix}/ping", tags=["系统"], summary="连通性测试")
    def ping() -> dict:
        """最简单的连通性验证。"""
        return {"pong": True}

    return app


app = create_app()
