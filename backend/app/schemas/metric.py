"""指标查询、看板与导出模型（阶段四 · 步骤 1-2、1-3、1-5）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class IndicatorPoint(BaseModel):
    """指标数据点（不含环比/同比）。"""

    metric_code: str = Field(description="指标编码 M01~M33")
    metric_name: str = Field(default="", description="指标名称")
    dim_value: str = Field(description="维度值：科室编码或 ALL")
    granularity: str = Field(description="粒度：day / month / period")
    stat_date: str = Field(description="统计日期 YYYY-MM-DD")
    metric_value: float | None = Field(default=None, description="指标值（数据源不足时为 null）")
    unit: str = Field(default="", description="单位")
    data_status: str = Field(default="OK", description="数据状态：OK / PENDING")
    theme: str = Field(default="", description="所属主题")


class IndicatorSeriesPoint(IndicatorPoint):
    """带同比 / 环比的数据点。"""

    prev_value: float | None = Field(default=None, description="上一期数值")
    mom: float | None = Field(default=None, description="环比变化率（%）")
    yoy: float | None = Field(default=None, description="同比变化率（%），无同期数据时为 null")
    change: float | None = Field(default=None, description="与上期差值")


class IndicatorSeriesOut(BaseModel):
    """一个指标的时序结果。"""

    metric_code: str
    metric_name: str = ""
    unit: str = ""
    granularity: str
    dim_value: str
    points: list[IndicatorSeriesPoint] = Field(default_factory=list)
    latest_value: float | None = None


class MetricQueryOut(BaseModel):
    """多指标查询结果（五大主题路由共用）。"""

    theme: str = Field(default="", description="主题，如 outpatient / inpatient / revenue / disease / resource")
    dims: list[str] = Field(default_factory=list, description="查询维度值列表")
    drill: str | None = Field(default=None, description="下钻维度：dept / month / metric")
    granularity: str = "month"
    date_range: list[str] = Field(default_factory=list, description="[start_date, end_date]")
    series: list[IndicatorSeriesOut] = Field(default_factory=list)
    row_count: int = 0


class DeptRankRow(BaseModel):
    """科室排行的单行。"""

    dept_code: str
    dept_name: str = ""
    metric_code: str = ""
    metric_name: str = ""
    metric_value: float | None = None
    unit: str = ""


class DashboardOverviewOut(BaseModel):
    """管理驾驶舱总览。"""

    period: list[str] = Field(default_factory=list, description="[start_date, end_date]")
    dept_scope: str = Field(default="ALL", description="数据范围：ALL 或科室编码")
    kpis: list[IndicatorSeriesPoint] = Field(default_factory=list, description="核心 KPI 卡片")
    trend: list[IndicatorSeriesPoint] = Field(default_factory=list, description="收入趋势（月粒度）")
    dept_rank: list[DeptRankRow] = Field(default_factory=list, description="科室排行")
    pending_metrics: list[str] = Field(default_factory=list, description="数据源待补充的指标编码")


class DeptTrendOut(BaseModel):
    """科室看板的单指标趋势。"""

    metric_code: str
    metric_name: str = ""
    unit: str = ""
    points: list[IndicatorSeriesPoint] = Field(default_factory=list)


class DeptRankOut(BaseModel):
    """科室横向排名的当前位次。"""

    metric_code: str = Field(default="M16", description="排名依据指标")
    metric_name: str = ""
    dept_code: str = ""
    rank: int | None = Field(default=None, description="该科室名次（1 起）")
    total_depts: int = Field(default=0, description="参与排名的科室数")
    metric_value: float | None = None
    unit: str = ""


class DeptStaffOut(BaseModel):
    """科室人力快照（来自人事系统人力台账）。"""

    stat_date: str | None = Field(default=None, description="台账统计日期")
    doctor_cnt: int = Field(default=0, description="在岗医师数")
    nurse_cnt: int = Field(default=0, description="在岗护士数")
    staff_total: int = Field(default=0, description="卫技人员合计")
    source: str = Field(default="HR 人力台账", description="数据来源")


class DeptBoardOut(BaseModel):
    """科室运营看板（单科室全指标视图）。"""

    dept_code: str
    dept_name: str = ""
    period: list[str] = Field(default_factory=list, description="[start_date, end_date]")
    granularity: str = "month"
    kpis: list[IndicatorSeriesPoint] = Field(default_factory=list, description="科室核心指标卡片")
    trends: list[DeptTrendOut] = Field(default_factory=list, description="床位使用率 / 平均住院日等趋势")
    composition: list[IndicatorSeriesPoint] = Field(default_factory=list, description="收入构成（费别口径）")
    rank: DeptRankOut | None = Field(default=None, description="科室收入横向名次")
    staff: DeptStaffOut = Field(default_factory=DeptStaffOut, description="科室人力快照")
    pending_metrics: list[str] = Field(default_factory=list, description="数据源待补充的指标编码")


class ExportOut(BaseModel):
    """导出结果。"""

    filename: str
    content_type: str
    row_count: int
    size_bytes: int
