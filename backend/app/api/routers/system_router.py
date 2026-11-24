"""系统管理接口（阶段五配套：角色、数据源、审计、告警通知）。

    GET  /api/system/roles                     角色目录（RBAC 三角色 + 权限说明）
    GET  /api/system/datasources               数据源注册清单（来自 etl/config/sources.json）
    POST /api/system/datasources/{name}/test   数据源连通性测试
    GET  /api/system/audits                    操作审计查询（管理员）
    GET  /api/system/alerts                    质量告警站内信（列表 + 未读数 + 及时率）
    POST /api/system/alerts/{alert_id}/read    标记单条告警已读
    POST /api/system/alerts/read-all           全部标记已读
    PUT  /api/auth/users/{user_id}             用户编辑（角色/科室/启停，仅管理员）
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.deps import CurrentUser, get_client_ip, get_current_user, require_role
from app.core.response import BusinessError, ok
from app.core.security import normalize_role
from app.schemas.auth import UserOut, UserUpdateIn
from app.schemas.common import ApiResponse, ErrorResponse
from app.schemas.task import AlertListOut, AlertTimeliness, DataSourceOut, RoleOut
from app.services import alert_service
from app.services.audit_service import list_audits, log_action

router = APIRouter(prefix="/system", tags=["系统管理"])

ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "参数校验失败"},
    401: {"model": ErrorResponse, "description": "未登录或令牌失效"},
    403: {"model": ErrorResponse, "description": "角色不足（需管理员）"},
}

# RBAC 角色目录（与《需求规格说明书》角色定义一致）
ROLE_CATALOG: list[dict[str, object]] = [
    {
        "role_code": "ADMIN",
        "role_name": "管理员",
        "description": "系统配置、用户与角色维护、数据源与任务管理、全部数据可见",
        "permissions": ["user:manage", "system:manage", "data:all", "task:trigger", "export:all"],
    },
    {
        "role_code": "ANALYST",
        "role_name": "运营分析师",
        "description": "全院数据分析、看板与报表、导出与质量报告查看",
        "permissions": ["data:all", "dashboard:view", "report:export", "quality:view"],
    },
    {
        "role_code": "DEPT_USER",
        "role_name": "科室用户",
        "description": "仅本科室数据的看板与分析，不可查看全院汇总与管理页",
        "permissions": ["data:dept", "dashboard:view", "report:export"],
    },
]


@router.get(
    "/roles",
    response_model=ApiResponse[list[RoleOut]],
    summary="角色目录",
    description="返回 RBAC 三角色（管理员 / 运营分析师 / 科室用户）及其权限点，供角色管理页展示。",
    responses=ERROR_RESPONSES,
)
def list_roles(_: CurrentUser = Depends(require_role("ADMIN"))) -> dict:
    """角色列表。"""
    return ok(ROLE_CATALOG)


@router.get(
    "/datasources",
    response_model=ApiResponse[list[DataSourceOut]],
    summary="数据源清单",
    description="读取 ETL 数据源注册表（5 类数据源 / 6 个接入对象）及其目标 ODS 表。",
    responses=ERROR_RESPONSES,
)
def list_datasources(_: CurrentUser = Depends(require_role("ADMIN", "ANALYST"))) -> dict:
    """数据源清单。"""
    from app.services.task_service import list_data_sources

    return ok(list_data_sources())


@router.post(
    "/datasources/{source_name}/test",
    response_model=ApiResponse[dict],
    summary="数据源连通性测试",
    description="文件类数据源校验文件可读与表头完整；数据库类数据源执行 SELECT 1 连通性探测。",
    responses=ERROR_RESPONSES,
)
def test_datasource(
    source_name: str,
    request: Request,
    background: BackgroundTasks,
    user: CurrentUser = Depends(require_role("ADMIN")),
) -> dict:
    """测试单个数据源。"""
    from app.services.task_service import test_data_source

    passed, message = test_data_source(source_name)
    log_action(
        background,
        user=user,
        action="test_datasource",
        resource=f"/api/system/datasources/{source_name}/test",
        detail=f"result={'OK' if passed else 'FAIL'} {message}",
        client_ip=get_client_ip(request),
    )
    if not passed:
        raise BusinessError(40001, message)
    return ok({"source_name": source_name, "connected": True, "message": message})


@router.get(
    "/audits",
    response_model=ApiResponse[list[dict]],
    summary="操作审计日志",
    description="按时间倒序返回登录、查询、导出、任务触发等审计记录（保留 ≥180 天）。",
    responses=ERROR_RESPONSES,
)
def get_audits(
    limit: int = Query(default=50, ge=1, le=500, description="返回条数"),
    action: str | None = Query(default=None, description="按动作过滤：login / query / export / trigger_task"),
    session: Session = Depends(get_session),
    _: CurrentUser = Depends(require_role("ADMIN")),
) -> dict:
    """审计日志查询。"""
    return ok(list_audits(session, limit=limit, action=action))


@router.get(
    "/alerts",
    response_model=ApiResponse[AlertListOut],
    summary="质量告警站内信",
    description="返回质量告警列表（按生成时间倒序）、未读条数与通知及时率统计；"
    "及时率 = 送达耗时 ≤ 阈值的告警数 / 告警总数。",
    responses=ERROR_RESPONSES,
)
def get_alerts(
    session: Session = Depends(get_session),
    unread_only: bool = Query(default=False, description="仅返回未读告警"),
    limit: int = Query(default=20, ge=1, le=200, description="返回条数"),
    batch_date: str | None = Query(default=None, description="批次业务日期 YYYY-MM-DD，缺省返回全部"),
    _: CurrentUser = Depends(get_current_user),
) -> dict:
    """告警列表（站内信通道）。"""
    return ok(alert_service.list_alerts(session, batch_date=batch_date, unread_only=unread_only, limit=limit))


@router.get(
    "/alerts/timeliness",
    response_model=ApiResponse[AlertTimeliness],
    summary="告警通知及时率",
    description="按批次统计告警总数、送达数、及时数与及时率（默认阈值 300 秒）。",
    responses=ERROR_RESPONSES,
)
def get_alert_timeliness(
    session: Session = Depends(get_session),
    batch_date: str | None = Query(default=None, description="批次业务日期，缺省统计全部"),
    _: CurrentUser = Depends(get_current_user),
) -> dict:
    """告警通知及时率统计。"""
    return ok(alert_service.timeliness(session, batch_date))


@router.post(
    "/alerts/read-all",
    response_model=ApiResponse[dict],
    summary="全部告警标记已读",
    description="把当前所有未读告警标记为已读，返回受影响条数。",
    responses=ERROR_RESPONSES,
)
def read_all_alerts(
    request: Request,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """全部标记已读。"""
    affected = alert_service.mark_all_read(session)
    log_action(
        background,
        user=user,
        action="read_alerts",
        resource="/api/system/alerts/read-all",
        detail=f"affected={affected}",
        client_ip=get_client_ip(request),
    )
    return ok({"affected": affected})


@router.post(
    "/alerts/{alert_id}/read",
    response_model=ApiResponse[dict],
    summary="标记单条告警已读",
    description="按告警 ID 标记已读，返回受影响条数（0 表示告警不存在或已读）。",
    responses=ERROR_RESPONSES,
)
def read_alert(
    alert_id: int,
    session: Session = Depends(get_session),
    _: CurrentUser = Depends(get_current_user),
) -> dict:
    """标记单条告警已读。"""
    affected = alert_service.mark_read(session, alert_id)
    return ok({"alert_id": alert_id, "affected": affected})


@router.put(
    "/users/{user_id}",
    response_model=ApiResponse[UserOut],
    summary="编辑用户（仅管理员）",
    description="修改角色、所属科室与启停状态；角色与科室变更即时生效（下次请求即以新权限校验）。",
    responses=ERROR_RESPONSES,
)
def update_user(
    user_id: int,
    payload: UserUpdateIn,
    request: Request,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
    current: CurrentUser = Depends(require_role("ADMIN")),
) -> dict:
    """编辑用户信息。"""
    from app.models.sys import SysUser

    user = session.execute(select(SysUser).where(SysUser.id == user_id)).scalar_one_or_none()
    if user is None:
        raise BusinessError(40401, f"用户不存在：{user_id}", status_code=status.HTTP_404_NOT_FOUND)

    if payload.role_code is not None:
        role = normalize_role(payload.role_code)
        if role not in {"ADMIN", "ANALYST", "DEPT_USER"}:
            raise BusinessError(40001, f"非法角色：{payload.role_code}")
        user.role_code = role
    if payload.dept_code is not None:
        user.dept_code = payload.dept_code or None
    if payload.real_name is not None:
        user.real_name = payload.real_name
    if payload.is_active is not None:
        user.is_active = int(payload.is_active)
    if normalize_role(user.role_code) == "DEPT_USER" and not user.dept_code:
        raise BusinessError(40001, "科室用户必须指定 dept_code")

    session.commit()
    session.refresh(user)
    log_action(
        background,
        user=current,
        action="update_user",
        resource=f"/api/system/users/{user_id}",
        detail=f"username={user.username} role={user.role_code} dept={user.dept_code or '-'} active={user.is_active}",
        client_ip=get_client_ip(request),
    )
    return ok(
        UserOut(
            id=user.id,
            username=user.username,
            real_name=user.real_name or "",
            role_code=normalize_role(user.role_code),
            dept_code=user.dept_code,
        )
    )
