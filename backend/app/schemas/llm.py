"""智能分析（大模型）相关模型（阶段六 · 步骤 3-4、1-3）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class NL2SQLQueryIn(BaseModel):
    """自然语言问数请求。"""

    question: str = Field(min_length=2, max_length=200, description="自然语言问题，如「上月呼吸科床位使用率趋势如何」")


class NL2SQLIntentOut(BaseModel):
    """解析出的查询意图。"""

    metric_code: str
    metric_name: str = ""
    dim_value: str | None = None
    dim_name: str = ""
    granularity: str = "period"
    date_range: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    source: str = "rule"


class NL2SQLDataPoint(BaseModel):
    """查询结果数据点。"""

    dim_value: str
    dept_name: str = ""
    stat_date: str
    metric_value: float | None = None
    unit: str = ""
    data_status: str = "OK"


class NL2SQLChartOut(BaseModel):
    """图表建议配置（前端直接渲染）。"""

    type: str = Field(default="trend_line", description="trend_line / rank_bar / kpi / empty")
    x_axis: list[str] = Field(default_factory=list)
    series: list[float | None] = Field(default_factory=list)
    series_name: str = ""


class NL2SQLResultOut(BaseModel):
    """问数三要素结果：指标数值 + 图表 + 解读。"""

    question: str
    intent: NL2SQLIntentOut
    sql: str = Field(description="实际执行（已渲染参数）的只读 SQL，供审计与复核")
    data: list[NL2SQLDataPoint] = Field(default_factory=list)
    chart: NL2SQLChartOut = Field(default_factory=NL2SQLChartOut)
    insight: str = ""
    row_count: int = 0


class CapabilityOut(BaseModel):
    """能力边界说明。"""

    metrics: list[dict] = Field(default_factory=list)
    dims: list[dict] = Field(default_factory=list)
    granularities: list[str] = Field(default_factory=list)
    window: list[str] = Field(default_factory=list)
    llm_available: bool = False
    examples: list[str] = Field(default_factory=list)


class ReportIn(BaseModel):
    """报告生成请求。"""

    report_type: str = Field(default="monthly", description="weekly 或 monthly")
    week: str | None = Field(default=None, description="周报参数：2025-W25 或 2025-06-23")
    month: str | None = Field(default=None, description="月报参数：2025-06")


class ReportChapterOut(BaseModel):
    heading: str
    text: str = ""
    metrics: dict = Field(default_factory=dict)
    text_source: str = "template"


class ReportOut(BaseModel):
    title: str
    period: dict = Field(default_factory=dict)
    previous_period: dict = Field(default_factory=dict)
    chapters: list[ReportChapterOut] = Field(default_factory=list)
    risk_items: list[str] = Field(default_factory=list)
    summary: str = ""
    llm_available: bool = False


class KBIn(BaseModel):
    """知识问答请求。"""

    question: str = Field(min_length=2, max_length=200, description="指标口径相关问题")


class KBRefOut(BaseModel):
    title: str
    ref: str = ""


class KBOut(BaseModel):
    question: str
    answer: str
    refs: list[KBRefOut] = Field(default_factory=list)
    matched: bool = False
    source: str = "manual_snippet"


class AnomalyIn(BaseModel):
    """异常归因请求。"""

    metric: str = Field(min_length=2, max_length=16, description="指标编码，如 M16")
    stat_date: str | None = Field(default=None, description="统计日期 YYYY-MM-DD，缺省取最新月")


class AnomalyItemOut(BaseModel):
    dim_value: str
    dept_name: str = ""
    current: float | None = None
    previous: float | None = None
    change: float | None = None
    change_rate: float | None = None
    contribution: float | None = None


class AnomalyOut(BaseModel):
    metric_code: str
    metric_name: str = ""
    stat_date: str = ""
    previous_date: str | None = None
    top: list[AnomalyItemOut] = Field(default_factory=list)
    hints: list[str] = Field(default_factory=list)
    note: str = ""
