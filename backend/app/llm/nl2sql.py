"""NL2SQL 核心链路（阶段六 · 步骤 3）。

    parse_intent(question)              解析自然语言问题中的时间、指标与维度意图
    map_metric_dim(intent)              把意图映射为指标编码与 dim 维表字段（含合法性校验）
    generate_sql(intent)                按模板生成只读 SQL（不直接执行）
    validate_sql(sql, user)             校验只读、表白名单、语法与角色数据权限
    run_nl_query(question, user, session) 编排：解析 → 映射 → 生成 → 校验 → 执行 → 组装结果

设计取舍（见《大模型应用设计说明》）：模板优先，模型只做意图解析；
因此未配置模型时链路依旧可用（离线规则引擎），配置模型后自动启用模型解析。
"""

from __future__ import annotations

import calendar
import re
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser
from app.core.response import BusinessError
from app.llm.catalog import (
    CN_MONTHS,
    DATASET_WINDOW,
    DEPT_ALIASES,
    DEPT_CATALOG,
    GRANULARITY_KEYWORDS,
    METRIC_ALIASES,
    METRIC_CATALOG,
    dept_name,
    dim_schema,
    metric_meta,
    metric_name,
)
from app.llm.client import get_client
from app.llm.prompts import build_nl2sql_prompt

# SQL 安全白名单
ALLOWED_TABLES = {"ads_indicator_result"}
FORBIDDEN_KEYWORDS = (
    "insert ", "update ", "delete ", "drop ", "alter ", "truncate ", "create ",
    "grant ", "revoke ", "attach ", "pragma ", "replace into", "into outfile",
    "--", "/*", "*/", ";",
)
MAX_ROWS = 500


@dataclass(frozen=True)
class QueryIntent:
    """结构化查询意图。"""

    metric_code: str
    metric_name: str
    dim_value: str | None      # None 表示全部维度（各科室）
    dim_name: str
    granularity: str
    start_date: str
    end_date: str
    confidence: float
    source: str = "rule"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------- 时间解析
def _month_range(year: int, month: int) -> tuple[str, str]:
    last_day = calendar.monthrange(year, month)[1]
    return f"{year}-{month:02d}-01", f"{year}-{month:02d}-{last_day:02d}"


def _window_months() -> tuple[int, int]:
    start = date.fromisoformat(DATASET_WINDOW[0])
    end = date.fromisoformat(DATASET_WINDOW[1])
    return start.year, end.month


def resolve_time_range(question: str) -> tuple[str, str] | None:
    """从问题中解析时间范围；无法识别时返回 None（交由默认统计期）。"""
    year, end_month = _window_months()

    explicit = re.search(r"(20\d{2})[-/年](\d{1,2})", question)
    if explicit:
        return _month_range(int(explicit.group(1)), int(explicit.group(2)))

    if any(word in question for word in ("上月", "上个月", "上一个")):
        prev = end_month - 1 if end_month > 1 else 12
        prev_year = year if end_month > 1 else year - 1
        return _month_range(prev_year, prev)

    if any(word in question for word in ("本月", "这个月", "当月")):
        return _month_range(year, end_month)

    for word, month in CN_MONTHS.items():
        if word in question:
            return _month_range(year, month)

    if any(word in question for word in ("全期", "统计期", "本季度", "整个季度", "整体", "整季")):
        return DATASET_WINDOW

    if any(word in question for word in ("近三个月", "这几个月", "三个月的趋势", "近期")):
        return DATASET_WINDOW

    return None


def parse_intent(question: str) -> dict[str, Any]:
    """解析问题意图：优先规则引擎，规则无法识别指标时再调用模型。"""
    if not question or not question.strip():
        raise BusinessError(40001, "问题不能为空")

    text_question = re.sub(r"\s+", "", question)
    metric_code = _match_metric(text_question)
    dim_value = _match_dim(text_question)
    time_range = resolve_time_range(text_question)
    # 问"趋势/变化"时按整个统计期取数，并强制月度粒度（单月无法体现趋势）
    trend_requested = any(
        word in text_question for word in ("趋势", "走势", "怎么变化", "变化情况", "变化趋势")
    )
    if trend_requested:
        time_range = DATASET_WINDOW
    granularity = "month" if trend_requested else _match_granularity(text_question, time_range)
    confidence = 0.9 if (metric_code and time_range) else (0.8 if metric_code else 0.4)
    source = "rule"

    if metric_code is None:
        llm_intent = _parse_with_llm(text_question)
        if llm_intent:
            metric_code = llm_intent.get("metric_code")
            dim_value = llm_intent.get("dim_value", dim_value)
            granularity = llm_intent.get("granularity", granularity) or granularity
            if llm_intent.get("start_date") and llm_intent.get("end_date"):
                time_range = (str(llm_intent["start_date"]), str(llm_intent["end_date"]))
            confidence = float(llm_intent.get("confidence", 0.7))
            source = "llm"

    return {
        "question": text_question,
        "metric_code": metric_code,
        "dim_value": dim_value,
        "granularity": granularity,
        "time_range": time_range,
        "confidence": confidence,
        "source": source,
    }


def _match_metric(question: str) -> str | None:
    """按别名词典匹配指标（长词优先）。"""
    for alias, code in METRIC_ALIASES:
        if alias in question:
            return code
    # 直接出现编码
    direct = re.search(r"M\d{2}", question.upper())
    if direct and direct.group(0) in METRIC_CATALOG:
        return direct.group(0)
    return None


def _match_dim(question: str) -> str | None:
    """匹配维度：返回科室编码；"各科室/排名/对比" 返回 None 表示全维度。"""
    if any(word in question for word in ("各科室", "科室排名", "科室对比", "科室排行", "分科室", "哪个科室")):
        return None
    for alias, code in DEPT_ALIASES:
        if alias in question:
            return code
    return "ALL"


def _match_granularity(question: str, time_range: tuple[str, str] | None = None) -> str:
    """判定粒度：显式关键词优先；指定了月份/上月的默认按月度，否则按全期。"""
    for keyword, value in GRANULARITY_KEYWORDS:
        if keyword in question:
            return value
    if time_range is not None and list(time_range) != list(DATASET_WINDOW):
        return "month"
    return "period"


def _parse_with_llm(question: str) -> dict[str, Any] | None:
    """模型解析（未配置模型或失败时返回 None）。"""
    client = get_client()
    payload, _call = client.chat_json(build_nl2sql_prompt(question, metric_meta(), dim_schema()))
    return payload


# ---------------------------------------------------------------- 映射与校验
def map_metric_dim(intent: dict[str, Any]) -> QueryIntent:
    """把意图映射为指标编码 + dim 维表字段，并做合法性校验。"""
    metric_code = intent.get("metric_code")
    if not metric_code or metric_code not in METRIC_CATALOG:
        raise BusinessError(
            40001,
            f"无法识别指标：{intent.get('question', '')}；请补充指标名称（如「上月呼吸科床位使用率趋势如何」）",
        )

    dim_value = intent.get("dim_value")
    if dim_value not in (None, *DEPT_CATALOG.keys()):
        raise BusinessError(40001, f"无法识别维度：{dim_value}，可选 {sorted(DEPT_CATALOG)}")

    granularity = intent.get("granularity") or "period"
    if granularity not in {"day", "month", "period"}:
        granularity = "period"

    time_range = intent.get("time_range") or DATASET_WINDOW
    start_date, end_date = _normalize_range(time_range, granularity)

    return QueryIntent(
        metric_code=str(metric_code),
        metric_name=metric_name(str(metric_code)),
        dim_value=dim_value,
        dim_name=dept_name(dim_value) if dim_value else "各科室",
        granularity=granularity,
        start_date=start_date,
        end_date=end_date,
        confidence=float(intent.get("confidence", 0.8)),
        source=str(intent.get("source", "rule")),
    )


def _normalize_range(time_range: tuple[str, str] | list[str], granularity: str) -> tuple[str, str]:
    """规整日期范围（月粒度统一到自然月末，便于与 ADS 结果表匹配）。"""
    try:
        start = date.fromisoformat(str(time_range[0])[:10])
        end = date.fromisoformat(str(time_range[1])[:10])
    except (ValueError, IndexError) as exc:
        raise BusinessError(40001, f"日期范围非法：{time_range}") from exc
    if start > end:
        start, end = end, start
    if granularity == "period":
        return DATASET_WINDOW[0], DATASET_WINDOW[1]
    if granularity == "month":
        # 月份对齐：起止都取自然月边界
        start = start.replace(day=1)
        end = end.replace(day=calendar.monthrange(end.year, end.month)[1])
    return start.isoformat(), end.isoformat()


def generate_sql(intent: QueryIntent) -> str:
    """按模板生成只读 SQL（命名参数占位，交由 validate_sql 校验后执行）。"""
    clauses = [
        "SELECT metric_code, metric_name, dim_value, granularity, stat_date, metric_value, unit, data_status",
        "FROM ads_indicator_result",
        "WHERE metric_code = :metric_code",
        "AND granularity = :granularity",
        "AND stat_date >= :start_date",
        "AND stat_date <= :end_date",
    ]
    if intent.dim_value is not None:
        clauses.append("AND dim_value = :dim_value")
    else:
        # 各科室口径下排除全院汇总行，避免科室排行被 ALL 拉高
        clauses.append("AND dim_value <> 'ALL'")
    clauses.append("ORDER BY dim_value, stat_date")
    clauses.append(f"LIMIT {MAX_ROWS}")
    return " ".join(clauses)


def validate_sql(sql: str, user: CurrentUser | None = None) -> str:
    """校验 SQL 只读、表白名单、无注入关键字，并按角色注入数据权限条件。"""
    normalized = " ".join(sql.split())
    lowered = normalized.lower()

    if not lowered.startswith("select "):
        raise BusinessError(40001, "仅允许只读查询（SELECT）")
    for keyword in FORBIDDEN_KEYWORDS:
        if keyword in lowered:
            raise BusinessError(40001, f"SQL 含禁止关键字：{keyword.strip() or keyword}")

    tables = set(re.findall(r"from\s+([a-zA-Z_][\w]*)", lowered))
    illegal = {table for table in tables if table not in ALLOWED_TABLES}
    if illegal:
        raise BusinessError(40001, f"SQL 访问了未授权的表：{sorted(illegal)}")
    if "limit" not in lowered:
        raise BusinessError(40001, "SQL 必须包含 LIMIT 限制返回行数")

    if user is not None and user.is_dept_scoped:
        if "dim_value = :dim_value" not in normalized:
            # 科室用户强制注入数据权限条件
            normalized = normalized.replace(
                "AND stat_date <= :end_date",
                "AND stat_date <= :end_date AND dim_value = :dim_value",
            )
        if "dim_value = :dim_value" not in normalized:
            raise BusinessError(40302, "数据越权：科室用户查询缺少科室过滤条件")
    return normalized


# ---------------------------------------------------------------- 执行与组装
def _render_sql_for_display(sql: str, params: dict[str, Any]) -> str:
    """把命名参数渲染成可读 SQL（仅用于展示与审计，不执行）。"""
    rendered = sql
    for key, value in params.items():
        literal = "NULL" if value is None else (f"'{value}'" if isinstance(value, str) else str(value))
        rendered = rendered.replace(f":{key}", literal)
    return rendered


def run_nl_query(
    question: str,
    user: CurrentUser | None,
    session: Session,
    *,
    use_llm: bool = True,
) -> dict[str, Any]:
    """编排：解析 → 映射 → 生成 SQL → 校验 → 只读执行 → 组装三要素结果。"""
    intent_raw = parse_intent(question) if use_llm else {
        "question": question,
        "metric_code": _match_metric(question),
        "dim_value": _match_dim(question),
        "granularity": _match_granularity(question, resolve_time_range(question)),
        "time_range": resolve_time_range(question),
        "confidence": 0.8,
        "source": "rule",
    }
    intent = map_metric_dim(intent_raw)

    # 科室用户强制使用本科室维度
    dim_value = intent.dim_value
    if user is not None and user.is_dept_scoped:
        dim_value = user.dept_code

    effective = QueryIntent(**{**intent.to_dict(), "dim_value": dim_value, "dim_name": dept_name(dim_value) if dim_value else "各科室"})
    sql = validate_sql(generate_sql(effective), user)
    params: dict[str, Any] = {
        "metric_code": effective.metric_code,
        "granularity": effective.granularity,
        "start_date": effective.start_date,
        "end_date": effective.end_date,
    }
    if effective.dim_value is not None:
        params["dim_value"] = effective.dim_value

    rows = session.execute(text(sql), params).mappings().all()
    data = [
        {
            "dim_value": row["dim_value"],
            "dept_name": dept_name(str(row["dim_value"])),
            "stat_date": row["stat_date"].isoformat() if hasattr(row["stat_date"], "isoformat") else str(row["stat_date"]),
            "metric_value": float(row["metric_value"]) if row["metric_value"] is not None else None,
            "unit": row["unit"],
            "data_status": row["data_status"],
        }
        for row in rows
    ]

    chart = _build_chart(data, effective)
    insight = _build_insight(data, effective)
    return {
        "question": question,
        "intent": {
            "metric_code": effective.metric_code,
            "metric_name": effective.metric_name,
            "dim_value": effective.dim_value,
            "dim_name": effective.dim_name,
            "granularity": effective.granularity,
            "date_range": [effective.start_date, effective.end_date],
            "confidence": effective.confidence,
            "source": effective.source,
        },
        "sql": _render_sql_for_display(sql, params),
        "data": data,
        "chart": chart,
        "insight": insight,
        "row_count": len(data),
    }


def _build_chart(data: list[dict[str, Any]], intent: QueryIntent) -> dict[str, Any]:
    """根据数据形态推荐图表类型（趋势折线 / 科室排行条形 / 单值指标卡）。"""
    depts = {item["dim_value"] for item in data}
    if not data:
        return {"type": "empty", "x_axis": [], "series": [], "series_name": intent.metric_name}
    if len(depts) > 1 or intent.dim_value is None:
        return {
            "type": "rank_bar",
            "x_axis": [item["dept_name"] for item in data],
            "series": [item["metric_value"] for item in data],
            "series_name": intent.metric_name,
        }
    if len(data) > 1:
        return {
            "type": "trend_line",
            "x_axis": [item["stat_date"] for item in data],
            "series": [item["metric_value"] for item in data],
            "series_name": intent.metric_name,
        }
    return {
        "type": "kpi",
        "x_axis": [data[0]["dept_name"]],
        "series": [data[0]["metric_value"]],
        "series_name": intent.metric_name,
    }


def _build_insight(data: list[dict[str, Any]], intent: QueryIntent) -> str:
    """生成文字解读（模板拼接，配置模型时可由模型润色）。"""
    scope = intent.dim_name
    period = f"{intent.start_date} ~ {intent.end_date}"
    if not data:
        return f"未查询到{scope}在 {period} 的{intent.metric_name}数据，请确认指标编码与时间范围。"

    pending = [item for item in data if item["data_status"] == "PENDING"]
    unit = data[0]["unit"] or ""
    if len(data) == 1:
        value = data[0]["metric_value"]
        if value is None:
            return f"{scope} {period} 的{intent.metric_name}暂无数据（数据源待补充）。"
        return (
            f"{scope} {period} 的{intent.metric_name}为 {value:,.4g} {unit}"
            f"（指标 {intent.metric_code}，口径见《指标口径手册》）。"
        )

    first, last = data[0], data[-1]
    if last["metric_value"] is None or first["metric_value"] is None:
        return f"{scope} {period} 的{intent.metric_name}存在数据源待补充项，暂无法给出变化结论。"

    if intent.dim_value is None:
        top = max(data, key=lambda item: item["metric_value"] or 0)
        return (
            f"{period} {intent.metric_name}按科室对比：{top['dept_name']}最高，为 {top['metric_value']:,.2f} {unit}；"
            f"共 {len({item['dim_value'] for item in data})} 个科室有数据。"
        )

    change = last["metric_value"] - first["metric_value"]
    rate = (change / first["metric_value"] * 100) if first["metric_value"] else None
    trend = "上升" if change > 0 else ("下降" if change < 0 else "持平")
    rate_text = f"，变化率 {rate:+.2f}%" if rate is not None else ""
    hint = "（注意：源数据存在建仓窗口首尾效应，单月口径需结合注释解读）" if intent.granularity != "period" else ""
    pending_hint = "；部分统计期数据源待补充" if pending else ""
    return (
        f"{scope} {intent.metric_name}在 {period} 呈{trend}趋势："
        f"由 {first['metric_value']:,.2f} {unit} 变化至 {last['metric_value']:,.2f} {unit}"
        f"（{change:+,.2f} {unit}{rate_text}）{hint}{pending_hint}。"
    )


def describe_capabilities() -> dict[str, Any]:
    """返回 NL2SQL 能力边界说明（供前端提示与评测使用）。"""
    return {
        "metrics": [{"code": code, "name": name} for code, (name, _theme, _unit) in METRIC_CATALOG.items()],
        "dims": [{"value": code, "name": name} for code, name in DEPT_CATALOG.items()],
        "granularities": ["day", "month", "period"],
        "window": list(DATASET_WINDOW),
        "llm_available": get_client().is_available,
        "examples": [
            "上月呼吸科床位使用率趋势如何",
            "本季度各科室门诊人次排名",
            "6月的药占比是多少",
            "儿科平均住院日这几个月怎么变化的",
        ],
    }


__all__ = [
    "QueryIntent",
    "parse_intent",
    "map_metric_dim",
    "generate_sql",
    "validate_sql",
    "run_nl_query",
    "resolve_time_range",
    "describe_capabilities",
    "ALLOWED_TABLES",
]
