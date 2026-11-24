"""管理驾驶舱、科室运营看板与导出接口（阶段四 · 步骤 1-3、1-5）。

    GET /api/dashboard/overview   聚合返回 KPI、趋势与科室排行
    GET /api/dashboard/dept       科室运营看板：单科室全指标 + 趋势 + 收入构成 + 名次 + 人力快照
    GET /api/dashboard/export     将查询结果导出为 xlsx / pdf 文件流
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.deps import CurrentUser, get_client_ip, get_current_user
from app.core.response import BusinessError, ok
from app.schemas.common import ApiResponse, ErrorResponse
from app.schemas.metric import DashboardOverviewOut, DeptBoardOut
from app.services import export_service, indicator_service
from app.services.audit_service import log_action

router = APIRouter(prefix="/dashboard", tags=["管理驾驶舱"])

ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "参数校验失败"},
    401: {"model": ErrorResponse, "description": "未登录或令牌失效"},
    403: {"model": ErrorResponse, "description": "数据越权"},
}


def _split(value: str | None) -> list[str] | None:
    if not value:
        return None
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or None


@router.get(
    "/overview",
    response_model=ApiResponse[DashboardOverviewOut],
    summary="驾驶舱总览",
    description="聚合返回核心 KPI 卡片（含环比/同比）、收入趋势与科室收入排行；科室用户仅返回本科室数据。",
    responses=ERROR_RESPONSES,
)
def get_overview(
    request: Request,
    background: BackgroundTasks,
    start_date: str | None = Query(default=None, description="统计开始日期 YYYY-MM-DD"),
    end_date: str | None = Query(default=None, description="统计结束日期 YYYY-MM-DD"),
    granularity: str = Query(default="month", description="粒度：day / month / period"),
    top_n: int = Query(default=10, ge=1, le=30, description="科室排行取前 N"),
    session: Session = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """获取驾驶舱总览数据。"""
    date_range = [start_date, end_date] if start_date and end_date else None
    overview = indicator_service.get_overview(
        session, date_range, granularity, user=user, top_n=top_n
    )
    log_action(
        background,
        user=user,
        action="query",
        resource="/api/dashboard/overview",
        detail=f"period={overview['period']} scope={overview['dept_scope']} kpis={len(overview['kpis'])}",
        client_ip=get_client_ip(request),
    )
    return ok(overview)


@router.get(
    "/dept",
    response_model=ApiResponse[DeptBoardOut],
    summary="科室运营看板",
    description="返回单科室的核心指标卡片、床位使用率/平均住院日等趋势、费别收入构成、"
    "科室收入横向名次与人事系统人力快照；科室用户仅可查看本科室。",
    responses=ERROR_RESPONSES,
)
def get_dept_board(
    request: Request,
    background: BackgroundTasks,
    dept: str | None = Query(default=None, description="科室编码（如 HN）；科室用户缺省为本科室"),
    start_date: str | None = Query(default=None, description="统计开始日期 YYYY-MM-DD"),
    end_date: str | None = Query(default=None, description="统计结束日期 YYYY-MM-DD"),
    granularity: str = Query(default="month", description="粒度：day / month / period"),
    session: Session = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """获取科室运营看板数据。"""
    date_range = [start_date, end_date] if start_date and end_date else None
    board = indicator_service.get_dept_board(session, dept, date_range, granularity, user=user)
    log_action(
        background,
        user=user,
        action="query",
        resource="/api/dashboard/dept",
        detail=f"dept={board['dept_code']} period={board['period']} kpis={len(board['kpis'])}",
        client_ip=get_client_ip(request),
    )
    return ok(board)


@router.get(
    "/export",
    summary="导出查询结果（xlsx / pdf）",
    description="按当前查询条件生成 Excel 或 PDF 文件流；返回二进制流，不包裹统一外壳。",
    responses={
        200: {"content": {"application/octet-stream": {}}, "description": "文件流"},
        **ERROR_RESPONSES,
    },
)
def export_result(
    request: Request,
    background: BackgroundTasks,
    metric: str = Query(default="M16", description="指标编码"),
    dims: str | None = Query(default=None, description="维度值，逗号分隔"),
    start_date: str | None = Query(default=None, description="统计开始日期"),
    end_date: str | None = Query(default=None, description="统计结束日期"),
    granularity: str = Query(default="month", description="粒度"),
    file_format: str = Query(default="xlsx", alias="format", description="文件格式：xlsx / pdf"),
    session: Session = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    """导出指标查询结果为文件流。"""
    if file_format not in {"xlsx", "pdf"}:
        raise BusinessError(40001, f"不支持的文件格式：{file_format}，可选 xlsx / pdf")

    date_range = [start_date, end_date] if start_date and end_date else None
    result = indicator_service.list_metrics(
        session, [metric], _split(dims), date_range, granularity, theme="export", user=user
    )
    rows = export_service.rows_from_series(result["series"])
    if not rows:
        raise BusinessError(40401, "查询结果为空，无法导出", status_code=404)

    if file_format == "xlsx":
        payload, filename, mime = export_service.export_excel(rows, title=f"指标导出_{metric}")
    else:
        payload, filename, mime = export_service.export_pdf(rows, title=f"指标报表_{metric}")

    log_action(
        background,
        user=user,
        action="export",
        resource="/api/dashboard/export",
        detail=f"metric={metric} format={file_format} rows={len(rows)}",
        client_ip=get_client_ip(request),
    )
    return StreamingResponse(
        iter([payload]),
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
