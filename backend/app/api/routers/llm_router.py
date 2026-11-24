"""大模型应用接口（阶段六 · 步骤 3-4、1-3）。

    GET  /api/llm/capabilities   能力边界（指标/维度/粒度/示例）
    POST /api/llm/query          自然语言问数（NL2SQL）
    POST /api/llm/report         运营报告生成（周报 / 月报）
    POST /api/llm/kb             指标口径知识问答
    POST /api/llm/anomaly        异常波动归因

全部接口依赖登录鉴权并写入审计；模型超时（30s）或调用失败时降级为规则/模板结果，
链路异常统一返回 50301 错误结构，服务不崩溃。
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.deps import CurrentUser, get_client_ip, get_current_user
from app.core.response import BusinessError, ok
from app.llm import kb as kb_module
from app.llm import report_gen
from app.llm.nl2sql import describe_capabilities, run_nl_query
from app.schemas.common import ApiResponse, ErrorResponse
from app.schemas.llm import (
    AnomalyIn,
    AnomalyOut,
    CapabilityOut,
    KBIn,
    KBOut,
    NL2SQLQueryIn,
    NL2SQLResultOut,
    ReportIn,
    ReportOut,
)
from app.services.audit_service import log_action

router = APIRouter(prefix="/llm", tags=["智能分析"])

ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "参数校验失败或意图无法识别"},
    401: {"model": ErrorResponse, "description": "未登录或令牌失效"},
    403: {"model": ErrorResponse, "description": "数据越权"},
    404: {"model": ErrorResponse, "description": "无可用数据"},
    503: {"model": ErrorResponse, "description": "模型或依赖服务不可用（已降级）"},
}


@router.get(
    "/capabilities",
    response_model=ApiResponse[CapabilityOut],
    summary="智能问数能力边界",
    description="返回可问的指标、维度、时间粒度、统计窗口与示例问题，以及当前是否已接入大模型。",
    responses=ERROR_RESPONSES,
)
def get_capabilities(_: CurrentUser = Depends(get_current_user)) -> dict:
    """能力边界说明。"""
    return ok(describe_capabilities())


@router.post(
    "/query",
    response_model=ApiResponse[NL2SQLResultOut],
    summary="自然语言问数（NL2SQL）",
    description="解析问题意图 → 生成只读 SQL → 校验（白名单/只读/数据权限）→ 执行 → 返回数值、图表与解读。",
    responses=ERROR_RESPONSES,
)
def ask_question(
    payload: NL2SQLQueryIn,
    request: Request,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """自然语言问数。"""
    try:
        result = run_nl_query(payload.question, user, session)
    except BusinessError:
        log_action(
            background,
            user=user,
            action="ai_query",
            resource="/api/llm/query",
            detail=f"question={payload.question} result=FAIL",
            result="FAIL",
            client_ip=get_client_ip(request),
        )
        raise
    except Exception as exc:  # noqa: BLE001 - 统一降级为 503 错误结构
        raise BusinessError(50301, f"智能问数服务异常：{type(exc).__name__}", status_code=503) from exc

    log_action(
        background,
        user=user,
        action="ai_query",
        resource="/api/llm/query",
        detail=(
            f"question={payload.question} metric={result['intent']['metric_code']} "
            f"dim={result['intent']['dim_value']} rows={result['row_count']}"
        ),
        client_ip=get_client_ip(request),
    )
    return ok(result)


@router.post(
    "/report",
    response_model=ApiResponse[ReportOut],
    summary="运营报告生成",
    description="按周（weekly）或按月（monthly）生成四章节运营报告，数值来自真实查询，文字可模板或模型生成。",
    responses=ERROR_RESPONSES,
)
def generate_report(
    payload: ReportIn,
    request: Request,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """生成周报 / 月报。"""
    report_type = (payload.report_type or "monthly").lower()
    try:
        if report_type == "weekly":
            report = report_gen.gen_weekly_report(session, payload.week or "2025-W25")
        elif report_type == "monthly":
            report = report_gen.gen_monthly_report(session, payload.month or "2025-06")
        else:
            raise BusinessError(40001, f"不支持的报告类型：{payload.report_type}，可选 weekly / monthly")
    except BusinessError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise BusinessError(50301, f"报告生成失败：{type(exc).__name__}: {exc}", status_code=503) from exc

    log_action(
        background,
        user=user,
        action="ai_report",
        resource="/api/llm/report",
        detail=f"type={report_type} period={report['period']['label']}",
        client_ip=get_client_ip(request),
    )
    return ok(report)


@router.post(
    "/kb",
    response_model=ApiResponse[KBOut],
    summary="指标口径知识问答",
    description="基于《指标口径手册》片段检索 + 模型组织答案；未收录的口径明确告知，不做猜测。",
    responses=ERROR_RESPONSES,
)
def ask_kb(
    payload: KBIn,
    request: Request,
    background: BackgroundTasks,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """口径知识问答。"""
    try:
        answer = kb_module.kb_answer(payload.question)
    except Exception as exc:  # noqa: BLE001
        raise BusinessError(50301, f"知识问答服务异常：{type(exc).__name__}", status_code=503) from exc

    log_action(
        background,
        user=user,
        action="ai_kb",
        resource="/api/llm/kb",
        detail=f"question={payload.question} matched={answer['matched']} source={answer['source']}",
        client_ip=get_client_ip(request),
    )
    return ok(answer)


@router.post(
    "/anomaly",
    response_model=ApiResponse[AnomalyOut],
    summary="异常波动归因",
    description="计算指定指标环比波动最大的 Top3 科室，返回波动幅度、贡献度与归因提示。",
    responses=ERROR_RESPONSES,
)
def analyze(
    payload: AnomalyIn,
    request: Request,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """异常归因分析。"""
    try:
        result = report_gen.analyze_anomaly(session, payload.metric, payload.stat_date)
    except BusinessError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise BusinessError(50301, f"归因分析失败：{type(exc).__name__}", status_code=503) from exc

    log_action(
        background,
        user=user,
        action="ai_anomaly",
        resource="/api/llm/anomaly",
        detail=f"metric={payload.metric} date={result['stat_date']} top={len(result['top'])}",
        client_ip=get_client_ip(request),
    )
    return ok(result)
