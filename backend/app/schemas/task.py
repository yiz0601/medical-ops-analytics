"""任务监控与数据质量模型（阶段四 · 步骤 1-4）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TaskRunStatus(BaseModel):
    """采集 / 计算任务运行状态。"""

    task_name: str = Field(description="任务名：init_dim / extract_ods / clean_dwd / quality_check / dwd_wide / aggregate_dws / ads_indicators / indicator_reconcile")
    status: str = Field(description="最近一次状态：SUCCESS / FAILED / SKIPPED / UNKNOWN")
    rows: int = Field(default=0, description="处理行数")
    cost_ms: float = Field(default=0.0, description="耗时（毫秒）")
    log_time: str = Field(default="", description="日志时间")
    error: str = Field(default="", description="失败信息")


class TaskStatusOut(BaseModel):
    """任务状态列表。"""

    total: int = 0
    succeeded: int = 0
    failed: int = 0
    tasks: list[TaskRunStatus] = Field(default_factory=list)


class TaskTriggerIn(BaseModel):
    """手动触发任务。"""

    task_name: str = Field(description="任务名（白名单：extract_ods / clean_dwd / dwd_wide / aggregate_dws / ads_indicators）")
    start_date: str | None = Field(default=None, description="统计期开始日期 YYYY-MM-DD")
    end_date: str | None = Field(default=None, description="统计期结束日期 YYYY-MM-DD")


class TaskTriggerOut(BaseModel):
    """触发结果。"""

    task_name: str
    accepted: bool = True
    status: str = "SUCCESS"
    rows: int = 0
    message: str = ""


class QualityAlert(BaseModel):
    """质量告警项。"""

    rule_code: str
    rule_name: str = ""
    table: str = ""
    level: str = "WARN"
    status: str = ""
    failed: int = 0
    detail: str = ""


class QualityReportOut(BaseModel):
    """数据质量报告。"""

    batch_date: str = ""
    score: float = 0.0
    coverage_rate: float = 0.0
    total_rules: int = 0
    passed: int = 0
    warn: int = 0
    failed: int = 0
    blocking: bool = False
    generate_time: str = ""
    alerts: list[QualityAlert] = Field(default_factory=list)
