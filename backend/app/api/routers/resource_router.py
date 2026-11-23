"""资源效率分析路由（阶段四 · 步骤 1-3）。

统一走指标查询网关：`GET /api/resource/metrics`，支持下钻维度 drill=dept|month|metric。
默认指标集合见 `indicator_service.THEME_METRICS["resource"]`。
"""

from __future__ import annotations

from app.api.routers._theme_factory import build_theme_router
from app.services.indicator_service import THEME_METRICS

router = build_theme_router(
    theme="resource",
    prefix="/resource",
    tag="资源效率分析",
    summary="资源效率主题指标查询",
    description="床位使用率、平均住院日、医师人均门诊人次、床护比、百元医疗收入耗材消耗（M11/M12/M28–M30）",
    default_metrics=THEME_METRICS["resource"],
)