"""services 层单元测试（阶段四 · 步骤 3-3）。

    test_query_indicator     覆盖正常、空数据、非法 granularity 分支
    test_compare_yoy_mom     校验环比 / 同比 / 变化率计算
    test_export_service      校验 Excel / PDF 导出文件生成且非空
"""

from __future__ import annotations

import pytest

from app.core.deps import CurrentUser
from app.core.response import BusinessError
from app.services import export_service, indicator_service


def _analyst() -> CurrentUser:
    return CurrentUser(user_id=2, username="analyst01", role="ANALYST", dept_code=None)


def _dept_user() -> CurrentUser:
    return CurrentUser(user_id=3, username="dept_hn", role="DEPT_USER", dept_code="HN")


# ---------------------------------------------------------------- query_indicator
def test_query_indicator_normal(db_session):
    """正常分支：返回按日期升序的指标数据点。"""
    points = indicator_service.query_indicator(
        db_session, "M01", ["ALL"], ["2025-04-01", "2025-06-30"], "month", user=_analyst()
    )
    assert len(points) == 3
    assert [p["stat_date"] for p in points] == ["2025-04-30", "2025-05-31", "2025-06-30"]
    assert points[-1]["metric_value"] is not None
    assert points[-1]["dim_value"] == "ALL"
    assert points[-1]["theme"] == "门诊"


def test_query_indicator_empty(db_session):
    """空数据分支：未知指标返回空列表。"""
    points = indicator_service.query_indicator(
        db_session, "M99", ["ALL"], ["2025-04-01", "2025-06-30"], "month", user=_analyst()
    )
    assert points == []


def test_query_indicator_invalid_granularity(db_session):
    """非法 granularity：抛出 BusinessError(40001)。"""
    with pytest.raises(BusinessError) as exc:
        indicator_service.query_indicator(
            db_session, "M01", ["ALL"], ["2025-04-01", "2025-06-30"], "hour", user=_analyst()
        )
    assert exc.value.code == 40001


def test_query_indicator_invalid_drill_and_date(db_session):
    """非法下钻维度与反向日期区间均被拒绝。"""
    with pytest.raises(BusinessError):
        indicator_service.query_indicator(db_session, "M01", None, None, "month", drill="unknown")
    with pytest.raises(BusinessError):
        indicator_service.query_indicator(
            db_session, "M01", None, ["2025-06-30", "2025-04-01"], "month"
        )


def test_query_indicator_data_scope(db_session):
    """数据隔离：科室用户只能看到本科室数据，看不到 ALL 汇总行。"""
    points = indicator_service.query_indicator(
        db_session, "M01", ["ALL", "EK", "HN"], ["2025-04-01", "2025-06-30"], "month", user=_dept_user()
    )
    assert points, "科室用户应能查到本科室数据"
    assert {p["dim_value"] for p in points} <= {"HN"}


# ---------------------------------------------------------------- compare_yoy_mom
def test_compare_yoy_mom():
    """环比与同比：环比基于上一期，同比基于去年同期。"""
    points = [
        {"dim_value": "ALL", "stat_date": "2024-05-31", "metric_value": 100.0},
        {"dim_value": "ALL", "stat_date": "2024-06-30", "metric_value": 110.0},
        {"dim_value": "ALL", "stat_date": "2025-05-31", "metric_value": 120.0},
        {"dim_value": "ALL", "stat_date": "2025-06-30", "metric_value": 150.0},
    ]
    enriched = indicator_service.compare_yoy_mom(points)
    by_date = {item["stat_date"]: item for item in enriched}

    june = by_date["2025-06-30"]
    assert june["prev_value"] == 120.0
    assert june["change"] == pytest.approx(30.0)
    assert june["mom"] == pytest.approx(25.0)  # (150-120)/120
    assert june["yoy"] == pytest.approx(150 / 110 * 100 - 100, rel=1e-6)  # vs 2024-06-30

    first = by_date["2024-05-31"]
    assert first["prev_value"] is None and first["mom"] is None and first["yoy"] is None


def test_compare_yoy_mom_zero_and_missing():
    """边界：上一期为 0 或缺失时环比为 None；非法日期不参与计算。"""
    points = [
        {"dim_value": "EK", "stat_date": "2025-04-30", "metric_value": 0.0},
        {"dim_value": "EK", "stat_date": "2025-05-31", "metric_value": 50.0},
        {"dim_value": "EK", "stat_date": "not-a-date", "metric_value": 60.0},
    ]
    enriched = indicator_service.compare_yoy_mom(points)
    may = next(item for item in enriched if item["stat_date"] == "2025-05-31")
    assert may["prev_value"] == 0.0
    assert may["mom"] is None  # 分母为 0
    assert may["yoy"] is None  # 无同期


# ---------------------------------------------------------------- list_metrics / overview
def test_list_metrics_and_overview(db_session):
    """多指标查询与驾驶舱总览结构。"""
    result = indicator_service.list_metrics(
        db_session, ["M01", "M16"], ["ALL"], ["2025-04-01", "2025-06-30"], "month", theme="outpatient", user=_analyst()
    )
    assert result["theme"] == "outpatient"
    assert result["row_count"] == 6
    assert len(result["series"]) == 2
    assert result["series"][0]["points"][0]["mom"] is None  # 首月无环比

    overview = indicator_service.get_overview(db_session, ["2025-04-01", "2025-06-30"], "month", user=_analyst())
    assert overview["dept_scope"] == "ALL"
    assert len(overview["kpis"]) >= 5
    assert overview["trend"], "应有收入趋势数据"
    assert overview["dept_rank"], "应有科室排行"
    assert overview["dept_rank"][0]["metric_value"] >= overview["dept_rank"][-1]["metric_value"]
    assert "M27" in overview["pending_metrics"]  # 数据源待补充指标

    dept_overview = indicator_service.get_overview(db_session, None, "month", user=_dept_user())
    assert dept_overview["dept_scope"] == "HN"


def test_list_metrics_unknown_metric_returns_empty_series(db_session):
    """未知指标返回空序列而不是报错（前端显示空态）。"""
    result = indicator_service.list_metrics(
        db_session, ["M99"], None, None, "month", theme="outpatient", user=_analyst()
    )
    assert result["series"][0]["points"] == []
    assert result["series"][0]["latest_value"] is None


# ---------------------------------------------------------------- export_service
def test_export_service():
    """Excel / PDF 导出：内容非空且 MIME 正确。"""
    rows = [
        {
            "metric_code": "M01",
            "metric_name": "门诊人次",
            "dim_value": "ALL",
            "granularity": "month",
            "stat_date": "2025-06-30",
            "metric_value": 9000.0,
            "unit": "人次",
            "data_status": "OK",
        }
    ]
    xlsx, xlsx_name, xlsx_mime = export_service.export_excel(rows, title="指标导出")
    assert xlsx and len(xlsx) > 1000
    assert xlsx[:2] == b"PK"  # xlsx 为 zip 容器
    assert xlsx_name.endswith(".xlsx")
    assert xlsx_mime == export_service.EXCEL_MIME

    pdf, pdf_name, pdf_mime = export_service.export_pdf(rows, title="指标报表")
    assert pdf and pdf.startswith(b"%PDF")
    assert pdf_name.endswith(".pdf")
    assert pdf_mime == export_service.PDF_MIME


def test_rows_from_series_and_empty_export():
    """时序结果拍平为导出行；空数据时导出行数为 0。"""
    series = [
        {
            "metric_code": "M01",
            "metric_name": "门诊人次",
            "unit": "人次",
            "points": [
                {"metric_code": "M01", "metric_name": "门诊人次", "dim_value": "ALL", "granularity": "month",
                 "stat_date": "2025-04-30", "metric_value": 1.0, "unit": "人次", "data_status": "OK"},
                {"metric_code": "M01", "metric_name": "门诊人次", "dim_value": "ALL", "granularity": "month",
                 "stat_date": "2025-05-31", "metric_value": 2.0, "unit": "人次", "data_status": "OK"},
            ],
        }
    ]
    rows = export_service.rows_from_series(series)
    assert len(rows) == 2
    assert rows[0]["metric_code"] == "M01"
    assert export_service.rows_from_series([]) == []
