"""收入分析路由（阶段四 · 步骤 1-3）。

统一走指标查询网关：`GET /api/revenue/metrics`，支持下钻维度 drill=dept|month|metric。
默认指标集合见 `indicator_service.THEME_METRICS["revenue"]`。
"""

from __future__ import annotations

from app.api.routers._theme_factory import build_theme_router
from app.services.indicator_service import THEME_METRICS

router = build_theme_router(
    theme="revenue",
    prefix="/revenue",
    tag="收入分析",
    summary="收入主题指标查询",
    description="医疗收入合计、药品/耗材收入、药占比、耗占比、检查检验与医疗服务性收入占比、收入增长率（M16–M22/M33）",
    default_metrics=THEME_METRICS["revenue"],
)