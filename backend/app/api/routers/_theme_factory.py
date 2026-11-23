"""主题指标查询路由工厂（阶段四 · 步骤 1-3）。

五大主题路由（门诊 / 住院 / 收入 / 病种 / 资源效率）共用同一套查询网关：
`GET /api/{theme}/metrics?metrics=&dims=&start_date=&end_date=&granularity=&drill=`
统一走 `indicator_service.list_metrics`，保证口径与权限逻辑只有一份实现。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.deps import CurrentUser, get_current_user
from app.core.response import ok
from app.schemas.common import ApiResponse, ErrorResponse
from app.schemas.metric import MetricQueryOut
from app.services import indicator_service

ERROR_RESPONSES = {
    401: {"model": ErrorResponse, "description": "未登录或令牌失效"},
    403: {"model": ErrorResponse, "description": "无权限或数据越权"},
    422: {"model": ErrorResponse, "description": "参数校验失败"},
}


def _split(value: str | None) -> list[str] | None:
    if not value:
        return None
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or None


def build_theme_router(
    *,
    theme: str,
    prefix: str,
    tag: str,
    summary: str,
    description: str,
    default_metrics: list[str],
    drill_options: str = "dept,month,metric",
) -> APIRouter:
    """构建一个主题指标查询路由。"""
    router = APIRouter(prefix=prefix, tags=[tag])

    @router.get(
        "/metrics",
        response_model=ApiResponse[MetricQueryOut],
        summary=summary,
        description=description,
        responses=ERROR_RESPONSES,
    )
    def list_metrics(
        metrics: str | None = Query(
            default=None,
            description=f"指标编码，逗号分隔；缺省为主题默认指标（{','.join(default_metrics)}）",
            examples=[",".join(default_metrics[:3])],
        ),
        dims: str | None = Query(default=None, description="维度值（科室编码或 ALL），逗号分隔；缺省查全部"),
        start_date: str | None = Query(default=None, description="统计开始日期 YYYY-MM-DD"),
        end_date: str | None = Query(default=None, description="统计结束日期 YYYY-MM-DD"),
        granularity: str = Query(default="month", description="粒度：day / month / period"),
        drill: str | None = Query(default=None, description=f"下钻维度：{drill_options}"),
        session: Session = Depends(get_session),
        user: CurrentUser = Depends(get_current_user),
    ) -> dict:
        """按指标、维度、日期范围与粒度查询该主题指标，支持下钻维度标注。"""
        codes = _split(metrics) or default_metrics
        result = indicator_service.list_metrics(
            session,
            codes,
            _split(dims),
            [start_date, end_date] if start_date and end_date else None,
            granularity,
            theme=theme,
            user=user,
            drill=drill,
        )
        return ok(result)

    return router
