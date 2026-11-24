"""准确性与对账脚本（阶段七 · 步骤 6）。

    reconcile(sample_metrics=10)  抽样指标与服务链路 vs 独立手工 SQL 对账，返回误差与整体结论

对账口径：
    1. 服务链路：`indicator_service.query_indicator`（应用层取数 + 序列化）
    2. 手工 SQL：直接对 `ads_indicator_result` 执行参数化查询（绕过服务层）
    3. 另附月度合计 vs 全期值的一致性检查（仅对可加型指标做参考对比，不判定失败）
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

SAMPLE_METRICS = ["M01", "M03", "M08", "M10", "M11", "M12", "M16", "M19", "M24", "M31"]
ADDITIVE_METRICS = {"M01", "M06", "M08", "M09", "M10", "M07", "M15", "M16", "M17", "M18"}
TOLERANCE = 0.01


def reconcile(db_session, sample_metrics: int = 10) -> dict[str, Any]:
    """抽样指标对账：服务链路 vs 手工 SQL，返回 {sampled, passed, failed, max_abs_error, conclusion}。"""
    from app.core.deps import CurrentUser
    from app.services.indicator_service import query_indicator

    analyst = CurrentUser(user_id=2, username="analyst01", role="ANALYST", dept_code=None)
    metrics = SAMPLE_METRICS[: max(1, int(sample_metrics))]

    details: list[dict[str, Any]] = []
    max_error = 0.0
    passed = 0

    for metric in metrics:
        # 服务链路
        points = query_indicator(db_session, metric, ["ALL"], ["2025-04-01", "2025-06-30"], "period", user=analyst)
        service_value = points[-1]["metric_value"] if points else None

        # 手工 SQL（独立查询）
        manual_value = db_session.execute(
            text(
                "SELECT metric_value FROM ads_indicator_result "
                "WHERE metric_code = :metric AND dim_value = 'ALL' AND granularity = 'period' "
                "ORDER BY stat_date DESC LIMIT 1"
            ),
            {"metric": metric},
        ).scalar()
        manual_value = float(manual_value) if manual_value is not None else None

        if service_value is None and manual_value is None:
            error = 0.0
        elif service_value is None or manual_value is None:
            error = None
        else:
            error = abs(float(service_value) - manual_value)
            max_error = max(max_error, error)
        ok = error is not None and error <= TOLERANCE
        passed += 1 if ok else 0

        # 月度合计 vs 全期（仅可加型指标参考）
        monthly_sum = db_session.execute(
            text(
                "SELECT SUM(metric_value) FROM ads_indicator_result "
                "WHERE metric_code = :metric AND dim_value = 'ALL' AND granularity = 'month'"
            ),
            {"metric": metric},
        ).scalar()
        monthly_sum = float(monthly_sum) if monthly_sum is not None else None
        additive_gap = None
        if metric in ADDITIVE_METRICS and monthly_sum is not None and manual_value not in (None, 0):
            additive_gap = round((monthly_sum - manual_value) / manual_value * 100, 4)

        details.append(
            {
                "metric_code": metric,
                "service_value": None if service_value is None else round(float(service_value), 4),
                "manual_sql_value": None if manual_value is None else round(manual_value, 4),
                "abs_error": None if error is None else round(error, 6),
                "passed": ok,
                "monthly_sum": None if monthly_sum is None else round(monthly_sum, 4),
                "month_vs_period_pct": additive_gap,
            }
        )

    total = len(details)
    return {
        "sampled": total,
        "passed": passed,
        "failed": total - passed,
        "max_abs_error": round(max_error, 6),
        "tolerance": TOLERANCE,
        "conclusion": "全部抽样指标与手工 SQL 一致（误差在容差内）" if passed == total else "存在偏差，需排查取数链路",
        "details": details,
    }


def test_reconcile(db_session):
    """抽样 10 项指标对账，误差应全部在容差内。"""
    report = reconcile(db_session, sample_metrics=10)
    assert report["sampled"] == 10
    assert report["passed"] == report["sampled"], f"对账未通过：{report['details']}"
    assert report["max_abs_error"] <= report["tolerance"]


def test_reconcile_single_metric(db_session):
    """边界：抽样数量为 1 与超出样本量时均能正常执行。"""
    single = reconcile(db_session, sample_metrics=1)
    assert single["sampled"] == 1
    many = reconcile(db_session, sample_metrics=50)
    assert many["sampled"] == len(SAMPLE_METRICS)
