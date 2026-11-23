"""数据质量报告接口（阶段四 · 步骤 1-4）。

    GET /api/quality/report   返回指定批次的数据质量报告（评分、覆盖率、告警清单）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.deps import CurrentUser, get_current_user, require_role
from app.core.response import ok
from app.schemas.common import ApiResponse, ErrorResponse
from app.schemas.task import QualityReportOut
from app.services import task_service

router = APIRouter(prefix="/quality", tags=["数据质量"])

ERROR_RESPONSES = {
    401: {"model": ErrorResponse, "description": "未登录或令牌失效"},
    403: {"model": ErrorResponse, "description": "角色不足"},
    404: {"model": ErrorResponse, "description": "质量报告不存在"},
}


@router.get(
    "/report",
    response_model=ApiResponse[QualityReportOut],
    summary="数据质量报告",
    description="读取 backend/etl/logs/quality_report_YYYYMMDD.json，返回批次评分、规则覆盖率与告警清单。",
    responses=ERROR_RESPONSES,
)
def get_quality_report(
    batch_date: str | None = Query(default=None, description="批次业务日期 YYYY-MM-DD 或 YYYYMMDD；缺省取最新报告"),
    _: CurrentUser = Depends(require_role("ADMIN", "ANALYST")),
) -> dict:
    """获取质量报告。"""
    return ok(task_service.load_quality_report(batch_date))
