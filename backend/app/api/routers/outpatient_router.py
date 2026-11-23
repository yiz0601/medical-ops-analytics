"""门诊分析路由（阶段四 · 步骤 1-3）。

统一走指标查询网关：`GET /api/outpatient/metrics`，支持下钻维度 drill=dept|month|metric。
默认指标集合见 `indicator_service.THEME_METRICS["outpatient"]`。
"""

from __future__ import annotations

from app.api.routers._theme_factory import build_theme_router
from app.services.indicator_service import THEME_METRICS

router = build_theme_router(
    theme="outpatient",
    prefix="/outpatient",
    tag="门诊分析",
    summary="门诊主题指标查询",
    description="门诊人次、号别结构占比、次均费用、门急诊人次、门诊收入（M01/M02/M03/M06/M07）",
    default_metrics=THEME_METRICS["outpatient"],
)