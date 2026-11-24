"""指标查询服务（阶段四 · 步骤 1-2、1-3）。

    query_indicator(...)   按指标 + 维度 + 日期范围 + 粒度查询 ADS 层指标结果
    list_metrics(...)      多指标批量查询（五大主题路由共用同一查询网关）
    compare_yoy_mom(...)   计算序列的同比、环比与变化率
    get_overview(...)      管理驾驶舱总览：核心 KPI + 收入趋势 + 科室排行

数据来源：`ads_indicator_result`（指标结果表）与 `dim_department`（科室名称）。
所有查询均经过 `apply_data_scope` 做行级数据权限过滤。
"""

from __future__ import annotations

from datetime import date
from typing import Any, Iterable, Sequence

from sqlalchemy import Select, and_, select
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, apply_data_scope

# 主题 -> 指标编码（与 ADS 8 大主题集市、《指标口径手册》第 11 章一致）
THEME_METRICS: dict[str, list[str]] = {
    "outpatient": ["M01", "M02", "M03", "M06", "M07"],
    "inpatient": ["M08", "M09", "M10", "M11", "M12", "M13", "M14", "M15"],
    "revenue": ["M16", "M17", "M18", "M19", "M20", "M21", "M22", "M33"],
    "drug": ["M17", "M19"],
    "consumable": ["M18", "M20", "M30"],
    "disease": ["M23", "M24", "M25", "M26", "M27"],
    "resource": ["M11", "M12", "M28", "M29", "M30"],
    "service": ["M31", "M32"],
}

# 驾驶舱 KPI 卡片（顺序即展示顺序）
KPI_METRICS: list[str] = ["M01", "M08", "M11", "M12", "M16", "M19", "M24"]
TREND_METRIC = "M16"
RANK_METRIC = "M16"

ALLOWED_GRANULARITY = {"day", "month", "period"}
ALLOWED_DRILL = {"dept", "month", "metric", None}


def _ads_table():
    """延迟导入指标结果表（避免应用启动即加载 ETL 依赖）。"""
    from etl.config.mart_schema import ads_indicator_result

    return ads_indicator_result


def _dept_name_map() -> dict[str, str]:
    """科室编码 -> 名称（延迟读取字典配置，失败时降级为编码）。"""
    try:
        from etl.config.dicts import DEPT_NAME

        return dict(DEPT_NAME)
    except Exception:  # noqa: BLE001 - 维度字典不可用时降级
        return {}


def _normalize_granularity(granularity: str | None) -> str:
    value = (granularity or "month").lower()
    if value not in ALLOWED_GRANULARITY:
        from app.core.response import BusinessError

        raise BusinessError(40001, f"非法粒度：{granularity}，可选 {sorted(ALLOWED_GRANULARITY)}")
    return value


def _normalize_date_range(date_range: Sequence[str] | None) -> tuple[date, date]:
    """解析日期范围（默认取数据集统计期 2025-04-01 ~ 2025-06-30）。"""
    from app.core.response import BusinessError

    defaults = ("2025-04-01", "2025-06-30")
    if not date_range:
        start_str, end_str = defaults
    elif len(date_range) == 2:
        start_str, end_str = str(date_range[0]), str(date_range[1])
    else:
        raise BusinessError(40001, "date_range 需为 [开始日期, 结束日期] 两个值")

    try:
        start = date.fromisoformat(start_str[:10])
        end = date.fromisoformat(end_str[:10])
    except ValueError as exc:
        raise BusinessError(40001, f"日期格式非法：{exc}") from exc
    if start > end:
        raise BusinessError(40001, "开始日期不能晚于结束日期")
    return start, end


def _row_to_point(row: Any, dept_names: dict[str, str] | None = None) -> dict[str, Any]:
    """把结果表行转成数据点字典。"""
    names = dept_names if dept_names is not None else _dept_name_map()
    dim_value = str(row.dim_value)
    value = row.metric_value
    return {
        "metric_code": row.metric_code,
        "metric_name": row.metric_name or "",
        "dim_value": dim_value,
        "granularity": row.granularity,
        "stat_date": row.stat_date.isoformat() if hasattr(row.stat_date, "isoformat") else str(row.stat_date),
        "metric_value": float(value) if value is not None else None,
        "unit": row.unit or "",
        "data_status": row.data_status or "OK",
        "theme": row.theme or "",
        "dept_name": names.get(dim_value, "全院" if dim_value == "ALL" else dim_value),
    }


def query_indicator(
    session: Session,
    metric: str,
    dims: Sequence[str] | None = None,
    date_range: Sequence[str] | None = None,
    granularity: str | None = None,
    *,
    user: CurrentUser | None = None,
    drill: str | None = None,
) -> list[dict[str, Any]]:
    """按指标 + 维度 + 日期范围 + 粒度查询指标结果（升序）。

    参数
    ----
    metric       指标编码（M01~M33）
    dims         维度值列表（科室编码 / ALL），为空表示不限
    date_range   [开始日期, 结束日期]
    granularity  day / month / period
    user         当前用户（用于数据权限过滤）
    drill        下钻提示（dept/month/metric），仅用于响应标注
    """
    from app.core.response import BusinessError

    if drill not in ALLOWED_DRILL:
        raise BusinessError(40001, f"非法下钻维度：{drill}，可选 {sorted(x for x in ALLOWED_DRILL if x)}")
    if not metric:
        raise BusinessError(40001, "metric 不能为空")

    table = _ads_table()
    gran = _normalize_granularity(granularity)
    start, end = _normalize_date_range(date_range)

    stmt: Select = (
        select(table)
        .where(
            and_(
                table.c.metric_code == metric,
                table.c.granularity == gran,
                table.c.stat_date >= start,
                table.c.stat_date <= end,
            )
        )
        .order_by(table.c.dim_value, table.c.stat_date)
    )
    if dims:
        stmt = stmt.where(table.c.dim_value.in_(list(dims)))
    if user is not None:
        stmt = apply_data_scope(stmt, user)

    rows = session.execute(stmt).all()
    if not rows:
        return []
    names = _dept_name_map()
    return [_row_to_point(row._mapping, names) for row in rows]  # noqa: SLF001


def compare_yoy_mom(points: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """为序列补充上一期数值、环比、同比与变化率。

    * 环比 mom = (本期 − 上一期) / 上一期 × 100
    * 同比 yoy = (本期 − 去年同期) / 去年同期 × 100（无同期数据时为 None）
    """
    items = sorted(points, key=lambda item: (item["dim_value"], item["stat_date"]))
    by_date: dict[tuple[str, str], dict[str, Any]] = {(item["dim_value"], item["stat_date"]): item for item in items}
    enriched: list[dict[str, Any]] = []

    for item in items:
        point = dict(item)
        prev = by_date.get((item["dim_value"], _shift_period(item["stat_date"], -1)))
        last_year = by_date.get((item["dim_value"], _shift_period(item["stat_date"], -12)))

        prev_value = prev["metric_value"] if prev else None
        last_year_value = last_year["metric_value"] if last_year else None
        value = item["metric_value"]

        point["prev_value"] = prev_value
        point["change"] = round(value - prev_value, 4) if value is not None and prev_value is not None else None
        point["mom"] = (
            round((value - prev_value) / prev_value * 100, 4)
            if value is not None and prev_value not in (None, 0)
            else None
        )
        point["yoy"] = (
            round((value - last_year_value) / last_year_value * 100, 4)
            if value is not None and last_year_value not in (None, 0)
            else None
        )
        enriched.append(point)
    return enriched


def _shift_period(stat_date: str, months: int) -> str | None:
    """把 YYYY-MM-DD 平移若干个月（用于定位上一期 / 去年同期）。"""
    try:
        current = date.fromisoformat(stat_date[:10])
    except ValueError:
        return None
    total = current.year * 12 + (current.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    # 取该月最后一天，兼容月末日期（如 2025-06-30）
    import calendar

    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, last_day).isoformat()


def list_metrics(
    session: Session,
    metrics: Sequence[str],
    dims: Sequence[str] | None = None,
    date_range: Sequence[str] | None = None,
    granularity: str | None = None,
    *,
    theme: str = "",
    user: CurrentUser | None = None,
    drill: str | None = None,
) -> dict[str, Any]:
    """多指标批量查询（主题路由共用网关），返回各指标时序集合。"""
    from app.core.config import get_settings
    from app.core.response import BusinessError

    gran = _normalize_granularity(granularity)
    start, end = _normalize_date_range(date_range)
    settings = get_settings()

    series: list[dict[str, Any]] = []
    total_rows = 0
    for metric in metrics:
        raw = query_indicator(session, metric, dims, [start.isoformat(), end.isoformat()], gran, user=user, drill=drill)
        if not raw:
            series.append(
                {
                    "metric_code": metric,
                    "metric_name": "",
                    "unit": "",
                    "granularity": gran,
                    "dim_value": (dims[0] if dims else "ALL"),
                    "points": [],
                    "latest_value": None,
                }
            )
            continue
        total_rows += len(raw)
        if total_rows > settings.query_max_rows:
            raise BusinessError(40001, f"查询结果超过 {settings.query_max_rows} 行，请缩小日期范围或增加维度过滤")

        grouped: dict[str, list[dict[str, Any]]] = {}
        for point in raw:
            grouped.setdefault(point["dim_value"], []).append(point)
        for dim_value, points in grouped.items():
            enriched = compare_yoy_mom(points)
            series.append(
                {
                    "metric_code": metric,
                    "metric_name": points[0]["metric_name"],
                    "unit": points[0]["unit"],
                    "granularity": gran,
                    "dim_value": dim_value,
                    "points": enriched,
                    "latest_value": enriched[-1]["metric_value"] if enriched else None,
                }
            )

    return {
        "theme": theme,
        "dims": list(dims or []),
        "drill": drill,
        "granularity": gran,
        "date_range": [start.isoformat(), end.isoformat()],
        "series": series,
        "row_count": total_rows,
    }


def _latest(points: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    return points[-1] if points else None


def get_overview(
    session: Session,
    date_range: Sequence[str] | None = None,
    granularity: str | None = "month",
    *,
    user: CurrentUser | None = None,
    top_n: int = 10,
) -> dict[str, Any]:
    """管理驾驶舱总览：核心 KPI 卡片 + 收入趋势 + 科室收入排行 + 待补充指标。

    口径说明：
    * KPI 卡片使用**全期（period）**口径，与《指标口径手册》基线一致
      （如床位使用率 88.89%、平均住院日 9.54 天）；单月口径会受建仓窗口首尾效应影响。
    * 趋势使用请求指定的粒度（默认月），科室排行取最近一个统计期的科室值。
    """
    gran = _normalize_granularity(granularity)
    start, end = _normalize_date_range(date_range)
    period = [start.isoformat(), end.isoformat()]
    scope = user.dept_code if (user and user.is_dept_scoped) else "ALL"
    dims = [scope] if scope != "ALL" else ["ALL"]

    # KPI 卡片：全期口径（同比/环比在只有单个统计期时为 null）
    kpis: list[dict[str, Any]] = []
    for metric in KPI_METRICS:
        points = query_indicator(session, metric, dims, period, "period", user=user)
        if not points:
            continue
        enriched = compare_yoy_mom(points)
        latest = _latest(enriched)
        if latest is not None:
            kpis.append(latest)

    trend_points = query_indicator(session, TREND_METRIC, dims, period, gran, user=user)
    trend = compare_yoy_mom(trend_points)

    rank_points = query_indicator(session, RANK_METRIC, None, period, gran, user=user)
    latest_by_dept: dict[str, dict[str, Any]] = {}
    for point in rank_points:
        if point["dim_value"] == "ALL":
            continue
        latest_by_dept[point["dim_value"]] = point  # 已按日期升序，后者覆盖前者
    dept_rank = sorted(
        latest_by_dept.values(), key=lambda item: (item["metric_value"] or 0), reverse=True
    )[:top_n]

    pending = sorted(
        {
            point["metric_code"]
            for metric in THEME_METRICS["revenue"] + THEME_METRICS["disease"]
            for point in query_indicator(session, metric, dims, period, "period", user=user)
            if point["data_status"] == "PENDING"
        }
    )

    return {
        "period": period,
        "dept_scope": scope,
        "kpis": kpis,
        "trend": trend,
        "dept_rank": [
            {
                "dept_code": item["dim_value"],
                "dept_name": item.get("dept_name", ""),
                "metric_code": item["metric_code"],
                "metric_name": item["metric_name"],
                "metric_value": item["metric_value"],
                "unit": item["unit"],
            }
            for item in dept_rank
        ],
        "pending_metrics": pending,
    }


# 科室运营看板配置（管理驾驶舱之外的第三套看板）
DEPT_BOARD_KPIS: list[str] = ["M01", "M08", "M11", "M12", "M16", "M19", "M24", "M28"]
DEPT_BOARD_TRENDS: list[str] = ["M11", "M12", "M01", "M16"]
DEPT_BOARD_COMPOSITION: list[str] = ["M17", "M18", "M21", "M22"]
DEPT_BOARD_RANK_METRIC = "M16"


def _dept_staff_snapshot(session: Session, dept_code: str) -> dict[str, Any]:
    """读取科室人力台账最新快照（人事系统数据源接入后的 DWD 表）。"""
    try:
        from etl.config.dwd_schema import dwd_hr_staff_detail

        table = dwd_hr_staff_detail
        stmt = (
            select(table)
            .where(table.c.dept_code == dept_code)
            .order_by(table.c.stat_date.desc())
            .limit(1)
        )
        row = session.execute(stmt).mappings().first()
    except Exception:  # noqa: BLE001 - 人力台账未就绪时降级为空快照
        row = None
    if not row:
        return {"stat_date": None, "doctor_cnt": 0, "nurse_cnt": 0, "staff_total": 0, "source": "HR 人力台账（未就绪）"}
    return {
        "stat_date": row["stat_date"].isoformat() if row["stat_date"] else None,
        "doctor_cnt": int(row["doctor_cnt"] or 0),
        "nurse_cnt": int(row["nurse_cnt"] or 0),
        "staff_total": int(row["staff_total"] or 0),
        "source": "HR 人力台账",
    }


def get_dept_board(
    session: Session,
    dept: str | None = None,
    date_range: Sequence[str] | None = None,
    granularity: str | None = "month",
    *,
    user: CurrentUser | None = None,
) -> dict[str, Any]:
    """科室运营看板：单科室核心指标、趋势、收入构成、横向名次与人力快照。

    数据权限：科室用户（DEPT_USER）只能查看本科室；其请求其他科室时由
    `apply_data_scope` 过滤为空，与主题接口保持一致。
    """
    from app.core.response import BusinessError

    gran = _normalize_granularity(granularity)
    start, end = _normalize_date_range(date_range)
    period = [start.isoformat(), end.isoformat()]

    if not dept:
        dept = (user.dept_code if (user and user.is_dept_scoped) else "ALL") or "ALL"
    dept = str(dept)
    if user is not None and user.is_dept_scoped and dept not in {user.dept_code, "ALL"}:
        raise BusinessError(40301, f"无权查看科室 {dept} 的数据", status_code=403)
    if dept == "ALL":
        raise BusinessError(40001, "科室运营看板需指定科室编码，全院视角请使用管理驾驶舱")

    names = _dept_name_map()
    dept_name = names.get(dept, dept)

    # 1) 科室核心指标卡（全期口径）
    kpis: list[dict[str, Any]] = []
    pending: set[str] = set()
    for metric in DEPT_BOARD_KPIS:
        points = query_indicator(session, metric, [dept], period, "period", user=user)
        if not points:
            pending.add(metric)
            continue
        enriched = compare_yoy_mom(points)
        latest = _latest(enriched)
        if latest is None:
            continue
        if latest.get("data_status") == "PENDING":
            pending.add(metric)
        kpis.append(latest)

    # 2) 关键指标趋势（月粒度，含环比/同比）
    trends: list[dict[str, Any]] = []
    for metric in DEPT_BOARD_TRENDS:
        points = query_indicator(session, metric, [dept], period, gran, user=user)
        if not points:
            continue
        enriched = compare_yoy_mom(points)
        trends.append(
            {
                "metric_code": metric,
                "metric_name": enriched[0]["metric_name"],
                "unit": enriched[0]["unit"],
                "points": enriched,
            }
        )

    # 3) 费别构成（收入结构饼图）
    composition: list[dict[str, Any]] = []
    for metric in DEPT_BOARD_COMPOSITION:
        points = query_indicator(session, metric, [dept], period, "period", user=user)
        if not points:
            pending.add(metric)
            continue
        latest = _latest(compare_yoy_mom(points))
        if latest is not None:
            composition.append(latest)

    # 4) 横向名次（默认按医疗收入）
    rank: dict[str, Any] | None = None
    all_points = query_indicator(session, DEPT_BOARD_RANK_METRIC, None, period, gran, user=user)
    latest_by_dept: dict[str, dict[str, Any]] = {}
    for point in all_points:
        if point["dim_value"] == "ALL":
            continue
        latest_by_dept[point["dim_value"]] = point
    ordered = sorted(
        (item for item in latest_by_dept.values() if item["metric_value"] is not None),
        key=lambda item: item["metric_value"],
        reverse=True,
    )
    codes = [item["dim_value"] for item in ordered]
    if dept in codes and ordered:
        own = ordered[codes.index(dept)]
        rank = {
            "metric_code": DEPT_BOARD_RANK_METRIC,
            "metric_name": own["metric_name"],
            "dept_code": dept,
            "rank": codes.index(dept) + 1,
            "total_depts": len(codes),
            "metric_value": own["metric_value"],
            "unit": own["unit"],
        }

    return {
        "dept_code": dept,
        "dept_name": dept_name,
        "period": period,
        "granularity": gran,
        "kpis": kpis,
        "trends": trends,
        "composition": composition,
        "rank": rank,
        "staff": _dept_staff_snapshot(session, dept),
        "pending_metrics": sorted(pending),
    }
