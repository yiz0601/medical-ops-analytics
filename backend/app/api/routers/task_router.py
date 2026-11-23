"""采集 / 计算任务监控接口（阶段四 · 步骤 1-4）。

    GET  /api/task/status    查询采集 / 计算任务运行状态
    POST /api/task/trigger   手动触发指定任务（仅管理员）
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from app.core.deps import CurrentUser, get_client_ip, get_current_user, require_role
from app.core.response import ok
from app.schemas.common import ApiResponse, ErrorResponse
from app.schemas.task import TaskStatusOut, TaskTriggerIn, TaskTriggerOut
from app.services import task_service
from app.services.audit_service import log_action

router = APIRouter(prefix="/task", tags=["采集任务"])

ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "参数校验失败"},
    401: {"model": ErrorResponse, "description": "未登录或令牌失效"},
    403: {"model": ErrorResponse, "description": "角色不足（手动触发需管理员）"},
    503: {"model": ErrorResponse, "description": "任务执行失败"},
}


@router.get(
    "/status",
    response_model=ApiResponse[TaskStatusOut],
    summary="任务运行状态",
    description="读取 ETL 任务日志，返回每个任务最近一次运行的状态、行数与耗时。",
    responses=ERROR_RESPONSES,
)
def get_task_status(_: CurrentUser = Depends(get_current_user)) -> dict:
    """查询任务运行状态。"""
    return ok(task_service.get_task_status())


@router.post(
    "/trigger",
    response_model=ApiResponse[TaskTriggerOut],
    summary="手动触发任务（仅管理员）",
    description="白名单任务可手动重跑：extract_ods / clean_dwd / dwd_wide / aggregate_dws / ads_indicators。",
    responses=ERROR_RESPONSES,
)
def trigger_task(
    payload: TaskTriggerIn,
    request: Request,
    background: BackgroundTasks,
    user: CurrentUser = Depends(require_role("ADMIN")),
) -> dict:
    """触发指定 ETL 任务。"""
    result = task_service.trigger_task(payload.task_name, payload.start_date, payload.end_date)
    log_action(
        background,
        user=user,
        action="trigger_task",
        resource="/api/task/trigger",
        detail=f"task={payload.task_name} rows={result['rows']}",
        client_ip=get_client_ip(request),
    )
    return ok(result)
