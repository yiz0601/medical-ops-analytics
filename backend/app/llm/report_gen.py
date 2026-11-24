"""运营报告自动生成与异常归因（阶段六 · 步骤 1）。

    gen_weekly_report(session, week)    生成指定周期的周报（4 章节，数值来自真实查询）
    gen_monthly_report(session, month)  生成指定月报（口径同周报，统计粒度为自然月）
    analyze_anomaly(session, metric, date)  计算指标 Top3 波动维度并给出归因提示

数据来源：`dws_dept_daily`（科室 × 日基础度量，可灵活按任意窗口聚合）+ `ads_indicator_result`（异常归因）。
配置模型时由模型润色章节文字，未配置时使用模板文字（数值始终来自数据库）。
"""

from __future__ import annotations

import calendar
import json
from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.response import BusinessError
from app.llm.catalog import DATASET_WINDOW, dept_name, metric_name
from app.llm.client import get_client
from app.llm.prompts import build_report_prompt

CHAPTER_METRICS: list[tuple[str, list[str]]] = [
    ("一、运营总览", ["M01", "M08", "M16"]),
    ("二、门诊运行", ["M01", "M03", "M07"]),
    ("三、住院运行", ["M08", "M11", "M12"]),
    ("四、收入结构", ["M16", "M17", "M19", "M20"]),
]

ADDITIVE_METRICS = {"M01", "M06", "M08", "M09", "M10", "M07", "M15", "M16", "M17", "M18"}


# ---------------------------------------------------------------- 时间窗口
def _month_bounds(year: int, month: int) -> tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _shift_month(anchor: date, months: int) -> date:
    total = anchor.year * 12 + (anchor.month - 1) + months
    year, month = divmod(total, 12)
    return date(year, month + 1, 1)


def resolve_week(week: str) -> tuple[date, date]:
    """解析周：支持 `2025-W25`、`2025-06-23`（取所在自然周周一至周日）。"""
    value = (week or "").strip()
    match = __import__("re").match(r"^(\d{4})-W(\d{1,2})$", value)
    if match:
        year, week_no = int(match.group(1)), int(match.group(2))
        iso_monday = date.fromisocalendar(year, week_no, 1)
        return iso_monday, iso_monday + timedelta(days=6)
    try:
        anchor = date.fromisoformat(value[:10])
    except ValueError as exc:
        raise BusinessError(40001, f"周参数非法：{week}，示例 2025-W25 或 2025-06-23") from exc
    monday = anchor - timedelta(days=anchor.weekday())
    return monday, monday + timedelta(days=6)


def resolve_month(month: str) -> tuple[date, date]:
    """解析月：支持 `2025-06` 或 `2025-06-15`。"""
    value = (month or "").strip()
    match = __import__("re").match(r"^(\d{4})-(\d{1,2})", value)
    if not match:
        raise BusinessError(40001, f"月份参数非法：{month}，示例 2025-06")
    return _month_bounds(int(match.group(1)), int(match.group(2)))


# ---------------------------------------------------------------- 指标聚合
_SQL = """
SELECT
  COALESCE(SUM(op_visit_cnt), 0)            AS op_visit_cnt,
  COALESCE(SUM(op_fee_sum), 0)              AS op_fee_sum,
  COALESCE(SUM(ip_discharge_cnt), 0)        AS ip_discharge_cnt,
  COALESCE(SUM(ip_admit_cnt), 0)            AS ip_admit_cnt,
  COALESCE(SUM(bed_days), 0)                AS bed_days,
  COALESCE(SUM(bed_cnt), 0)                 AS bed_cnt_days,
  COALESCE(SUM(ip_fee_sum), 0)              AS ip_fee_sum,
  COALESCE(SUM(charge_amt_sum), 0)          AS total_amt,
  COALESCE(SUM(charge_drug_amt), 0)         AS drug_amt,
  COALESCE(SUM(charge_consumable_amt), 0)   AS consumable_amt,
  COALESCE(SUM(charge_exam_lab_amt), 0)     AS exam_lab_amt,
  COALESCE(SUM(charge_service_amt), 0)      AS service_amt,
  COALESCE(SUM(op_charge_amt), 0)           AS op_amt,
  COALESCE(SUM(ip_charge_amt), 0)           AS ip_amt,
  COALESCE(SUM(fin_revenue), 0)             AS fin_revenue,
  COALESCE(SUM(fin_drug_revenue), 0)        AS fin_drug_revenue,
  COALESCE(SUM(fin_consumable_revenue), 0)  AS fin_consumable_revenue,
  COALESCE(SUM(lis_report_cnt), 0)          AS lis_report_cnt,
  COALESCE(SUM(lis_abnormal_cnt), 0)        AS lis_abnormal_cnt
FROM dws_dept_daily
WHERE stat_date >= :start_date AND stat_date <= :end_date
"""


def _fetch_window(session: Session, start: date, end: date) -> dict[str, float]:
    row = session.execute(text(_SQL), {"start_date": start, "end_date": end}).mappings().first()
    return {key: float(value or 0) for key, value in dict(row or {}).items()}


def _safe_div(num: float, den: float, scale: float = 1.0) -> float | None:
    return round(num * scale / den, 4) if den else None


def compute_window_metrics(session: Session, start: date, end: date) -> dict[str, dict[str, Any]]:
    """按窗口计算报告所需核心指标（口径与《指标口径手册》一致）。"""
    data = _fetch_window(session, start, end)
    metrics: dict[str, dict[str, Any]] = {}

    def _put(code: str, value: float | None, unit: str) -> None:
        metrics[code] = {"value": value, "unit": unit, "name": metric_name(code)}

    _put("M01", data["op_visit_cnt"], "人次")
    _put("M03", _safe_div(data["op_fee_sum"], data["op_visit_cnt"]), "元")
    _put("M08", data["ip_discharge_cnt"], "人次")
    _put("M11", _safe_div(data["bed_days"], data["bed_cnt_days"], 100), "%")
    _put("M12", _safe_div(data["bed_days"], data["ip_discharge_cnt"]), "天")
    _put("M16", data["total_amt"], "元")
    _put("M07", data["op_amt"], "元")
    _put("M15", data["ip_amt"], "元")
    _put("M17", data["drug_amt"], "元")
    _put("M19", _safe_div(data["fin_drug_revenue"], data["fin_revenue"], 100), "%")
    _put("M20", _safe_div(data["fin_consumable_revenue"], data["fin_revenue"], 100), "%")
    _put("M21", _safe_div(data["exam_lab_amt"], data["total_amt"], 100), "%")
    _put("M32", _safe_div(data["lis_abnormal_cnt"], data["lis_report_cnt"], 100), "%")
    return metrics


def _pending_metrics(session: Session, start: date, end: date) -> list[str]:
    """查询窗口内数据源待补充的指标编码。"""
    rows = session.execute(
        text(
            "SELECT DISTINCT metric_code FROM ads_indicator_result "
            "WHERE data_status = 'PENDING' AND granularity = 'period'"
        )
    ).scalars().all()
    return sorted(str(code) for code in rows)


def _compare(previous: dict[str, dict[str, Any]], current: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """计算与上一窗口的变化。"""
    changes: dict[str, Any] = {}
    for code, item in current.items():
        prev_value = (previous.get(code) or {}).get("value")
        value = item.get("value")
        if value is None or prev_value in (None, 0):
            changes[code] = {"mom": None, "change": None}
            continue
        changes[code] = {
            "change": round(value - prev_value, 4),
            "mom": round((value - prev_value) / prev_value * 100, 2),
        }
    return changes


def _chapter_text(heading: str, metrics: dict[str, dict[str, Any]], changes: dict[str, Any]) -> str:
    """模板文字（无模型时的兜底）。"""
    parts: list[str] = []
    for code in CHAPTER_METRICS:
        pass
    mapping = {
        "一、运营总览": ["M01", "M08", "M16"],
        "二、门诊运行": ["M01", "M03", "M07"],
        "三、住院运行": ["M08", "M11", "M12"],
        "四、收入结构": ["M16", "M19", "M20"],
    }
    for code in mapping.get(heading, []):
        item = metrics.get(code) or {}
        value = item.get("value")
        if value is None:
            parts.append(f"{item.get('name', code)}数据源待补充。")
            continue
        unit = item.get("unit", "")
        mom = (changes.get(code) or {}).get("mom")
        mom_text = f"，环比 {mom:+.2f}%" if mom is not None else ""
        parts.append(f"{item.get('name', code)}为 {value:,.2f} {unit}{mom_text}。")
    return "".join(parts)


def _build_report(
    session: Session,
    start: date,
    end: date,
    *,
    title: str,
    period_label: str,
    use_llm: bool = True,
) -> dict[str, Any]:
    """组装报告：4 章节（数值 + 文字）、风险提示与结论。"""
    current = compute_window_metrics(session, start, end)
    span = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=span - 1)
    previous = compute_window_metrics(session, prev_start, prev_end) if prev_end >= date.fromisoformat(DATASET_WINDOW[0]) else {}
    changes = _compare(previous, current)

    client = get_client()
    use_model = use_llm and client.is_available
    chapters: list[dict[str, Any]] = []
    for heading, codes in CHAPTER_METRICS:
        payload = {
            code: {**current.get(code, {}), **(changes.get(code) or {})} for code in codes
        }
        chapter_text = _chapter_text(heading, current, changes)
        source = "template"
        if use_model:
            llm_payload, call = client.chat_json(build_report_prompt(heading, payload))
            if llm_payload and isinstance(llm_payload.get("chapters"), list) and llm_payload["chapters"]:
                chapter_text = str(llm_payload["chapters"][0].get("text") or chapter_text)
                source = "llm"
        chapters.append(
            {
                "heading": heading,
                "text": chapter_text,
                "metrics": payload,
                "text_source": source,
            }
        )

    pending = _pending_metrics(session, start, end)
    risk_items = [f"{metric_name(code)}（{code}）数据源待补充，未参与结论计算" for code in pending]
    risk_items.append("单月/单周口径受建仓窗口首尾效应影响（2025-06-30 集中出院 190 例），趋势解读需结合该注释")

    mom16 = (changes.get("M16") or {}).get("mom")
    mom_text = f"{mom16:+.2f}%" if mom16 is not None else "上期无数据"
    summary = (
        f"{period_label}：门诊 {current.get('M01', {}).get('value') or 0:,.0f} 人次，"
        f"出院 {current.get('M08', {}).get('value') or 0:,.0f} 人次，"
        f"医疗收入 {current.get('M16', {}).get('value') or 0:,.2f} 元"
        f"（环比 {mom_text}）。"
    )

    return {
        "title": title,
        "period": {"start": start.isoformat(), "end": end.isoformat(), "label": period_label},
        "previous_period": {"start": prev_start.isoformat(), "end": prev_end.isoformat()},
        "chapters": chapters,
        "risk_items": risk_items,
        "summary": summary,
        "metrics": current,
        "llm_available": client.is_available,
    }


def gen_weekly_report(session: Session, week: str, *, use_llm: bool = True) -> dict[str, Any]:
    """生成周报（周一到周日）。"""
    start, end = resolve_week(week)
    return _build_report(
        session, start, end, title="运营分析周报", period_label=f"{start.isoformat()} ~ {end.isoformat()}（周报）", use_llm=use_llm
    )


def gen_monthly_report(session: Session, month: str, *, use_llm: bool = True) -> dict[str, Any]:
    """生成月报（自然月）。"""
    start, end = resolve_month(month)
    return _build_report(
        session, start, end, title="运营分析月报", period_label=f"{start.year} 年 {start.month} 月（月报）", use_llm=use_llm
    )


# ---------------------------------------------------------------- 异常归因
def analyze_anomaly(
    session: Session,
    metric: str,
    stat_date: str | None = None,
    *,
    top_n: int = 3,
) -> dict[str, Any]:
    """计算指标环比波动最大的 Top N 维度，并给出归因提示。"""
    if not metric:
        raise BusinessError(40001, "metric 不能为空")

    dates = [
        str(value)
        for value in session.execute(
            text(
                "SELECT DISTINCT stat_date FROM ads_indicator_result "
                "WHERE metric_code = :metric AND granularity = 'month' AND dim_value <> 'ALL' ORDER BY stat_date DESC"
            ),
            {"metric": metric},
        ).scalars().all()
    ]
    if not dates:
        raise BusinessError(40401, f"指标 {metric} 无月粒度数据，无法做异常归因", status_code=404)

    target = stat_date or dates[0]
    if target not in dates:
        target = dates[0]
    index = dates.index(target)
    previous = dates[index + 1] if index + 1 < len(dates) else None

    current_rows = session.execute(
        text(
            "SELECT dim_value, metric_value FROM ads_indicator_result "
            "WHERE metric_code = :metric AND granularity = 'month' AND stat_date = :stat_date AND dim_value <> 'ALL'"
        ),
        {"metric": metric, "stat_date": target},
    ).mappings().all()
    previous_rows = (
        session.execute(
            text(
                "SELECT dim_value, metric_value FROM ads_indicator_result "
                "WHERE metric_code = :metric AND granularity = 'month' AND stat_date = :stat_date AND dim_value <> 'ALL'"
            ),
            {"metric": metric, "stat_date": previous},
        ).mappings().all()
        if previous
        else []
    )
    prev_map = {row["dim_value"]: float(row["metric_value"]) if row["metric_value"] is not None else None for row in previous_rows}

    items: list[dict[str, Any]] = []
    for row in current_rows:
        dim = str(row["dim_value"])
        value = float(row["metric_value"]) if row["metric_value"] is not None else None
        before = prev_map.get(dim)
        if value is None or before in (None, 0):
            continue
        change = value - before
        items.append(
            {
                "dim_value": dim,
                "dept_name": dept_name(dim),
                "current": round(value, 4),
                "previous": round(before, 4),
                "change": round(change, 4),
                "change_rate": round(change / before * 100, 2),
            }
        )

    items.sort(key=lambda item: abs(item["change_rate"]), reverse=True)
    top = items[:top_n]
    total_change = sum(item["change"] for item in items) or 0.0
    for item in top:
        item["contribution"] = round(item["change"] / total_change * 100, 2) if total_change else None

    hints: list[str] = []
    if top:
        hints.append(
            "波动最大的是 " + "、".join(f"{item['dept_name']}（{item['change_rate']:+.2f}%）" for item in top)
        )
        hints.append("建议结合该科室门诊量、出院人次与费别结构进一步下钻，排除建仓窗口首尾效应")
    if not previous:
        hints.append("上一期无同指标数据，无法计算环比，仅展示当期值")
    if any(item["current"] is None for item in top):
        hints.append("部分科室指标值为空，可能为数据源待补充或当期无业务")

    return {
        "metric_code": metric,
        "metric_name": metric_name(metric),
        "stat_date": target,
        "previous_date": previous,
        "top": top,
        "hints": hints,
        "note": "归因为统计相关提示，不构成因果结论",
    }


__all__ = [
    "resolve_week",
    "resolve_month",
    "compute_window_metrics",
    "gen_weekly_report",
    "gen_monthly_report",
    "analyze_anomaly",
    "ADDITIVE_METRICS",
]
