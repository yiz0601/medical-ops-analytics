"""医疗运营数据主题分析平台 —— FastAPI 应用入口。

启动方式（开发环境）：
    cd backend
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

接口文档：http://127.0.0.1:8000/docs
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

API_PREFIX = "/api/v1"

app = FastAPI(
    title="医疗运营数据主题分析平台 API",
    description="面向医院运营管理部门的一站式数据分析平台后端服务（指标查询 / 多维分析 / 看板 / 智能问数）",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url=f"{API_PREFIX}/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["系统"], summary="健康检查")
def health() -> dict:
    """容器健康探针接口，供 Docker Compose healthcheck 与 Nginx upstream 使用。"""
    return {"code": 0, "message": "success", "data": {"status": "up", "version": "0.1.0"}}


@app.get(f"{API_PREFIX}/ping", tags=["系统"], summary="连通性测试")
def ping() -> dict:
    return {"code": 0, "message": "success", "data": {"pong": True}}


# ---------------------------------------------------------------------------
# 路由注册位（后续按模块拆分到 app/api/ 下，逐个放开注释）
# ---------------------------------------------------------------------------
# from app.api import auth, system, datasource, task, file, quality
# from app.api import metric, dim, dashboard, analysis, report, ai
#
# app.include_router(auth.router, prefix=f"{API_PREFIX}/auth", tags=["认证鉴权"])
# app.include_router(system.router, prefix=f"{API_PREFIX}/system", tags=["系统管理"])
# app.include_router(datasource.router, prefix=f"{API_PREFIX}/datasource", tags=["数据源管理"])
# app.include_router(task.router, prefix=f"{API_PREFIX}/task", tags=["采集任务"])
# app.include_router(file.router, prefix=f"{API_PREFIX}/file", tags=["文件接入"])
# app.include_router(quality.router, prefix=f"{API_PREFIX}/quality", tags=["数据质量"])
# app.include_router(metric.router, prefix=f"{API_PREFIX}/metric", tags=["指标管理"])
# app.include_router(dim.router, prefix=f"{API_PREFIX}/dim", tags=["维度管理"])
# app.include_router(dashboard.router, prefix=f"{API_PREFIX}/dashboard", tags=["运营看板"])
# app.include_router(analysis.router, prefix=f"{API_PREFIX}/analysis", tags=["多维分析"])
# app.include_router(report.router, prefix=f"{API_PREFIX}/report", tags=["报表与导出"])
# app.include_router(ai.router, prefix=f"{API_PREFIX}/ai", tags=["智能分析"])
