"""API 路由总装（阶段四 · 步骤 1-3、1-4、2.1）。

统一前缀 `/api`，下挂：
    /auth         认证与用户
    /dashboard    管理驾驶舱与导出
    /outpatient   门诊分析     /inpatient 住院分析    /revenue 收入分析
    /disease      病种分析     /resource  资源效率分析
    /task         采集任务监控  /quality  数据质量报告
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import (
    auth_router,
    dashboard_router,
    disease_router,
    inpatient_router,
    outpatient_router,
    quality_router,
    resource_router,
    revenue_router,
    task_router,
)

api_router = APIRouter()

for module in (
    auth_router,
    dashboard_router,
    outpatient_router,
    inpatient_router,
    revenue_router,
    disease_router,
    resource_router,
    task_router,
    quality_router,
):
    api_router.include_router(module.router)

__all__ = ["api_router"]
