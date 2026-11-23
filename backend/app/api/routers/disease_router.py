"""病种分析路由（阶段四 · 步骤 1-3）。

统一走指标查询网关：`GET /api/disease/metrics`，支持下钻维度 drill=dept|month|metric。
默认指标集合见 `indicator_service.THEME_METRICS["disease"]`。
"""

from __future__ import annotations

from app.api.routers._theme_factory import build_theme_router
from app.services.indicator_service import THEME_METRICS

router = build_theme_router(
    theme="disease",
    prefix="/disease",
    tag="病种分析",
    summary="病种（DRG/DIP）主题指标查询",
    description="DRG 入组率、CMI、费用消耗指数、时间消耗指数、低风险组死亡率（M23–M27）",
    default_metrics=THEME_METRICS["disease"],
)