"""Prompt 资产（阶段六 · 步骤 2）。

    NL2SQL_PROMPT      三层结构：系统指令 / 指标口径 / 维度口径 + few-shot 示例
    build_nl2sql_prompt(question, metric_meta, dim_schema)  组装完整 Prompt
    REPORT_PROMPT      运营报告生成（章节结构与写作约束）
    KB_PROMPT          指标口径知识问答（必须引用口径手册条目）

设计原则（见《大模型应用设计说明》）：
    1. 模型只做"意图解析与文案组织"，SQL 由模板生成，避免口径漂移；
    2. 所有元数据以结构化 JSON 注入，禁止模型编造指标编码；
    3. 输出严格要求 JSON，便于程序校验与降级。
"""

from __future__ import annotations

import json
from typing import Any, Iterable

NL2SQL_SYSTEM_PROMPT = """你是医院运营数据分析助手。你的任务是把用户的中文问题解析为结构化查询意图（JSON），
不要输出 SQL，不要输出解释性文字。

强制规则：
1. metric_code 只能取给定指标目录中的编码（M01~M33），不得编造；
2. dim_value 只能取给定维度目录中的值（科室编码或 ALL），无法确定时取 ALL；
3. granularity 只能是 day / month / period 之一；问"趋势/走势"取 month，问"全期/整体/统计期"取 period；
4. 若问题缺少时间信息，start_date/end_date 置为 null；
5. 输出必须是单个 JSON 对象，字段：metric_code, dim_value, granularity, start_date, end_date, confidence。"""

NL2SQL_METRIC_PROMPT = """【指标口径目录】（编码 / 名称 / 主题 / 单位）
{metric_lines}

口径要点：
- 金额类指标区分"登记口径"（次均费用）与"流水口径"（收入合计），不得混用；
- 药占比、耗占比默认取财务口径；床位使用率分母为开放床位 × 统计天数。"""

NL2SQL_DIM_PROMPT = """【维度目录】（类型 / 取值 / 名称）
{dim_lines}

【时间说明】数据集统计期为 {window_start} ~ {window_end}；
"上月"指该窗口的最后一个月的前一个月，"本月"指窗口最后一个月。"""

NL2SQL_FEWSHOT: list[dict[str, str]] = [
    {
        "question": "上月呼吸科床位使用率趋势如何",
        "answer": '{"metric_code": "M11", "dim_value": "HN", "granularity": "month", "start_date": "2025-04-01", "end_date": "2025-06-30", "confidence": 0.95}',
    },
    {
        "question": "本季度各科室门诊人次排名",
        "answer": '{"metric_code": "M01", "dim_value": "ALL", "granularity": "period", "start_date": "2025-04-01", "end_date": "2025-06-30", "confidence": 0.95}',
    },
    {
        "question": "6月的药占比是多少",
        "answer": '{"metric_code": "M19", "dim_value": "ALL", "granularity": "month", "start_date": "2025-06-01", "end_date": "2025-06-30", "confidence": 0.92}',
    },
    {
        "question": "儿科平均住院日这几个月怎么变化的",
        "answer": '{"metric_code": "M12", "dim_value": "EK", "granularity": "month", "start_date": "2025-04-01", "end_date": "2025-06-30", "confidence": 0.9}',
    },
]

REPORT_PROMPT = """你是医院运营分析报告撰写助手。基于给定的指标数据撰写报告章节文字，要求：
1. 只使用给定数据，不得编造数值；缺失数据说明"数据源待补充"；
2. 每个章节 2~4 句话，先结论后依据，包含关键数值与环比变化；
3. 语言简洁专业，面向院领导与管理科室；
4. 输出 JSON：{{"chapters": [{{"heading": "...", "text": "..."}}], "summary": "..."}}。"""

KB_PROMPT = """你是医院运营指标口径问答助手。仅依据给定的口径手册片段回答，要求：
1. 回答中必须点明指标编码与口径要点；
2. 手册片段不足以回答时，明确说明"手册中未收录该口径"，不要猜测；
3. 输出 JSON：{{"answer": "...", "referenced": ["片段标题", ...]}}。"""


def _format_metric_lines(metric_meta: Iterable[dict[str, Any]]) -> str:
    return "\n".join(
        f"- {item['code']} / {item['name']} / {item.get('theme', '')} / {item.get('unit', '')}"
        for item in metric_meta
    )


def _format_dim_lines(dim_schema: Iterable[dict[str, Any]]) -> str:
    return "\n".join(
        f"- {item.get('dim_type', '')} / {item.get('dim_value', '')} / {item.get('dim_name', '')}"
        for item in dim_schema
    )


def build_nl2sql_prompt(
    question: str,
    metric_meta: Iterable[dict[str, Any]],
    dim_schema: Iterable[dict[str, Any]],
    window: tuple[str, str] = ("2025-04-01", "2025-06-30"),
) -> str:
    """组装三层 Prompt（系统指令 + 口径 + 维度 + few-shot + 问题）。"""
    metric_block = NL2SQL_METRIC_PROMPT.format(metric_lines=_format_metric_lines(metric_meta))
    dim_block = NL2SQL_DIM_PROMPT.format(
        dim_lines=_format_dim_lines(dim_schema), window_start=window[0], window_end=window[1]
    )
    fewshot = "\n".join(
        f"问题：{item['question']}\n输出：{item['answer']}" for item in NL2SQL_FEWSHOT
    )
    return (
        f"{NL2SQL_SYSTEM_PROMPT}\n\n{metric_block}\n\n{dim_block}\n\n"
        f"【示例】\n{fewshot}\n\n【待解析问题】\n{question}\n\n【输出】"
    )


def build_report_prompt(chapter_title: str, metrics_payload: dict[str, Any]) -> str:
    """组装报告章节生成 Prompt。"""
    return (
        f"{REPORT_PROMPT}\n\n【章节】{chapter_title}\n"
        f"【数据】{json.dumps(metrics_payload, ensure_ascii=False)}\n\n【输出】"
    )


def build_kb_prompt(question: str, snippets: Iterable[dict[str, Any]]) -> str:
    """组装知识问答 Prompt。"""
    rendered = "\n\n".join(
        f"片段标题：{item.get('title', '')}\n内容：{item.get('content', '')}" for item in snippets
    )
    return f"{KB_PROMPT}\n\n【手册片段】\n{rendered}\n\n【问题】{question}\n\n【输出】"
