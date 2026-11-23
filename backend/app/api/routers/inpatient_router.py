"""住院分析路由（阶段四 · 步骤 1-3）。

统一走指标查询网关：`GET /api/inpatient/metrics`，支持下钻维度 drill=dept|month|metric。
默认指标集合见 `indicator_service.THEME_METRICS["inpatient"]`。
"""

from __future__ import annotations

from app.api.routers._theme_factory import build_theme_router
from app.services.indicator_service import THEME_METRICS

router = build_theme_router(
    theme="inpatient",
    prefix="/inpatient",
    tag="住院分析",
    summary="住院主题指标查询",
    description="出入院人次、床日、床位使用率、平均住院日、次均费用、手术占比、住院收入（M08–M15）",
    default_metrics=THEME_METRICS["inpatient"],
)