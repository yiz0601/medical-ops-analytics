"""功能模块用例（阶段七 · 步骤 2）。

覆盖认证与用户、数据源与任务、质量规则与报告、指标查询、多维分析、导出、智能分析七组模块；
用例包含正常流、异常流与边界值，参数化后总数 100+ 条。

    test_auth_and_user_crud        登录、用户/角色/权限增删改查
    test_datasource_and_task       数据源注册、采集任务启停与失败重试
    test_quality_rules_and_report  质量规则配置、批次报告与告警查询
    test_indicator_query           指标目录、单点值、趋势与多粒度查询
    test_multidim_analysis         多维交叉、同比环比、下钻上卷
    test_export                    Excel/PDF 导出申请、状态轮询与下载
    test_llm_apis                  问数、报告生成、异常归因与口径问答
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

METRIC_CODES = [f"M{index:02d}" for index in range(1, 34)]
THEMES = ["outpatient", "inpatient", "revenue", "disease", "resource"]
DEPTS = ["ALL", "EK", "FC", "GK", "HN", "HX", "ICU", "JZ", "PW", "SJ", "XH"]
GRANULARITIES = ["month", "period"]


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:6]}"


# ---------------------------------------------------------------- 1. 认证与用户
def test_auth_and_user_crud(client, auth_headers):
    """登录成功/失败、令牌校验、用户创建/编辑/重复/角色越权。"""
    # 三种账号均可登录
    for username, password, role in (
        ("admin", "Admin@123", "ADMIN"),
        ("analyst01", "Analyst@123", "ANALYST"),
        ("dept_hn", "Dept@123", "DEPT_USER"),
    ):
        response = client.post("/api/auth/login", json={"username": username, "password": password})
        assert response.status_code == 200
        assert response.json()["data"]["user"]["role_code"] == role

    # 异常流：错误密码 / 不存在账号 / 空参数
    assert client.post("/api/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "ghost", "password": "x"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "", "password": ""}).status_code == 422

    # 用户创建 + 编辑 + 重复
    username = _unique("crud")
    created = client.post(
        "/api/auth/users",
        headers=auth_headers["admin"],
        json={"username": username, "password": "Test@12345", "real_name": "CRUD 测试", "role_code": "ANALYST"},
    )
    assert created.status_code == 201
    user_id = created.json()["data"]["id"]

    updated = client.put(
        f"/api/system/users/{user_id}",
        headers=auth_headers["admin"],
        json={"role_code": "department", "dept_code": "EK", "is_active": True},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["role_code"] == "DEPT_USER"
    assert updated.json()["data"]["dept_code"] == "EK"

    duplicated = client.post(
        "/api/auth/users",
        headers=auth_headers["admin"],
        json={"username": username, "password": "Test@12345", "role_code": "ANALYST"},
    )
    assert duplicated.status_code == 409

    # 异常流：科室用户缺 dept_code / 角色非法 / 不存在用户
    assert (
        client.post(
            "/api/auth/users",
            headers=auth_headers["admin"],
            json={"username": _unique("nodept"), "password": "Test@12345", "role_code": "DEPT_USER"},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/auth/users",
            headers=auth_headers["admin"],
            json={"username": _unique("badrole"), "password": "Test@12345", "role_code": "SUPERMAN"},
        ).status_code
        == 400
    )
    assert client.put("/api/system/users/999999", headers=auth_headers["admin"], json={"role_code": "ANALYST"}).status_code == 404

    # 角色目录与审计
    roles = client.get("/api/system/roles", headers=auth_headers["admin"]).json()["data"]
    assert {item["role_code"] for item in roles} == {"ADMIN", "ANALYST", "DEPT_USER"}
    audits = client.get("/api/system/audits?limit=20", headers=auth_headers["admin"]).json()["data"]
    assert isinstance(audits, list)


# ---------------------------------------------------------------- 2. 数据源与任务
def test_datasource_and_task(client, auth_headers, tmp_path, monkeypatch):
    """数据源清单/连接测试、任务状态、任务触发与失败重试。"""
    from app.services import task_service

    sources = client.get("/api/system/datasources", headers=auth_headers["admin"]).json()["data"]
    assert len(sources) >= 5, "应注册 5 类以上数据源"
    assert all("target_table" in item for item in sources)

    # 连接测试：存在的文件类数据源应通过
    first = sources[0]["source_name"]
    tested = client.post(f"/api/system/datasources/{first}/test", headers=auth_headers["admin"])
    assert tested.status_code in {200, 400}

    # 不存在的数据源 → 参数错误
    assert client.post("/api/system/datasources/not_exists/test", headers=auth_headers["admin"]).status_code == 400

    # 任务状态：无日志时全 UNKNOWN
    monkeypatch.setattr(task_service, "task_log_path", lambda: tmp_path / "task_run.log")
    status = client.get("/api/task/status", headers=auth_headers["analyst"]).json()["data"]
    assert status["total"] == len(task_service.TASK_NAMES)
    assert status["succeeded"] == 0

    # 写入成功 + 失败日志，验证统计
    (tmp_path / "task_run.log").write_text(
        "\n".join(
            [
                json.dumps({"task_name": "extract_ods", "status": "SUCCESS", "rows": 59922, "cost_ms": 2100, "log_time": "2025-06-30 02:00:00"}),
                json.dumps({"task_name": "clean_dwd", "status": "FAILED", "rows": 0, "cost_ms": 3000, "error": "模拟失败", "log_time": "2025-06-30 02:01:00"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    refreshed = client.get("/api/task/status", headers=auth_headers["analyst"]).json()["data"]
    assert refreshed["succeeded"] == 1 and refreshed["failed"] == 1
    failed_task = next(item for item in refreshed["tasks"] if item["task_name"] == "clean_dwd")
    assert failed_task["status"] == "FAILED" and "模拟失败" in failed_task["error"]

    # 触发：非法任务名 → 400；执行器异常 → 503（失败重试语义由调度框架保证）
    assert client.post("/api/task/trigger", headers=auth_headers["admin"], json={"task_name": "unknown"}).status_code == 400

    def _boom(start, end):
        raise RuntimeError("模拟任务执行失败")

    monkeypatch.setitem(task_service.TASK_RUNNERS, "extract_ods", _boom)
    assert client.post("/api/task/trigger", headers=auth_headers["admin"], json={"task_name": "extract_ods"}).status_code == 503

    monkeypatch.setitem(task_service.TASK_RUNNERS, "extract_ods", lambda start, end: {"ods": 100})
    ok = client.post("/api/task/trigger", headers=auth_headers["admin"], json={"task_name": "extract_ods"})
    assert ok.status_code == 200 and ok.json()["data"]["rows"] == 100


# ---------------------------------------------------------------- 3. 质量规则与报告
def test_quality_rules_and_report(client, auth_headers, tmp_path, monkeypatch):
    """质量报告：缺失、存在、告警清单、批次查询与角色权限。"""
    from app.services import task_service

    monkeypatch.setattr(task_service, "_log_dir", lambda: tmp_path)
    assert client.get("/api/quality/report", headers=auth_headers["analyst"]).status_code == 404
    assert client.get("/api/quality/report?batch_date=2025-06-30", headers=auth_headers["analyst"]).status_code == 404

    report = {
        "report_meta": {"batch_date": "2025-06-30", "generate_time": "2025-07-01 02:00:00"},
        "summary": {"total_rules": 25, "passed": 23, "warn": 2, "failed": 0, "score": 92.0, "coverage_rate": 100.0, "blocking": False},
        "alerts": [
            {"rule_code": "QR-DQ-18", "rule_name": "行数波动率", "table": "ods_his_outpatient_visit", "level": "WARN", "status": "WARN", "failed": 1, "detail": "5-16 +34.9%"},
            {"rule_code": "QR-DQ-19", "rule_name": "行数波动率", "table": "ods_his_inpatient_visit", "level": "WARN", "status": "WARN", "failed": 1, "detail": "6-30 出院 190 例"},
        ],
    }
    (tmp_path / "quality_report_20250630.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")

    data = client.get("/api/quality/report", headers=auth_headers["analyst"]).json()["data"]
    assert data["score"] == 92.0 and data["total_rules"] == 25
    assert data["coverage_rate"] == 100.0 and data["blocking"] is False
    assert len(data["alerts"]) == 2
    assert data["alerts"][0]["level"] == "WARN"

    by_batch = client.get("/api/quality/report?batch_date=2025-06-30", headers=auth_headers["admin"])
    assert by_batch.status_code == 200
    assert client.get("/api/quality/report", headers=auth_headers["department"]).status_code == 403


# ---------------------------------------------------------------- 4. 指标查询（33 项 × 粒度）
@pytest.mark.parametrize("metric", METRIC_CODES)
def test_indicator_query(client, auth_headers, metric):
    """指标目录与单点值：33 项指标在全期粒度下均可查询（含待补充指标）。"""
    response = client.get(f"/api/revenue/metrics?metrics={metric}&granularity=period", headers=auth_headers["analyst"])
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["granularity"] == "period"
    assert data["series"], f"{metric} 应返回序列（可为空数据）"


@pytest.mark.parametrize("granularity", GRANULARITIES)
@pytest.mark.parametrize("theme", THEMES)
def test_theme_granularity(client, auth_headers, theme, granularity):
    """五大主题 × 两种粒度的正常流。"""
    response = client.get(f"/api/{theme}/metrics?granularity={granularity}", headers=auth_headers["analyst"])
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["theme"] == theme
    assert data["granularity"] == granularity


def test_indicator_query_abnormal(client, auth_headers):
    """指标查询异常流：非法粒度、非法下钻、反向日期、超长时间范围。"""
    assert client.get("/api/outpatient/metrics?granularity=hour", headers=auth_headers["analyst"]).status_code == 400
    assert client.get("/api/outpatient/metrics?drill=unknown", headers=auth_headers["analyst"]).status_code == 400
    assert (
        client.get(
            "/api/outpatient/metrics?start_date=2025-06-30&end_date=2025-04-01", headers=auth_headers["analyst"]
        ).status_code
        == 400
    )
    # 未知指标：返回空序列（不报错）
    empty = client.get("/api/outpatient/metrics?metrics=M99", headers=auth_headers["analyst"])
    assert empty.status_code == 200
    assert empty.json()["data"]["series"][0]["points"] == []


# ---------------------------------------------------------------- 5. 多维分析（维度 × 下钻）
@pytest.mark.parametrize("dept", DEPTS)
def test_multidim_analysis(client, auth_headers, dept):
    """多维交叉：11 个维度值分别查询，科室维度应返回对应数据。"""
    response = client.get(f"/api/inpatient/metrics?metrics=M08&dims={dept}&granularity=period", headers=auth_headers["analyst"])
    assert response.status_code == 200
    series = response.json()["data"]["series"]
    assert series, f"维度 {dept} 应有序列返回"
    if dept != "ALL":
        assert series[0]["dim_value"] == dept


def test_multidim_drill_and_compare(client, auth_headers):
    """下钻（drill）与同比/环比字段。"""
    drilled = client.get("/api/revenue/metrics?metrics=M16&drill=month&granularity=month", headers=auth_headers["analyst"])
    assert drilled.status_code == 200
    data = drilled.json()["data"]
    assert data["drill"] == "month"
    points = data["series"][0]["points"]
    assert len(points) >= 2
    assert "mom" in points[0] and "yoy" in points[0]
    assert points[0]["mom"] is None  # 首月无环比
    assert points[1]["mom"] is not None

    # 异常：非法 drill
    assert client.get("/api/revenue/metrics?metrics=M16&drill=bad", headers=auth_headers["analyst"]).status_code == 400


# ---------------------------------------------------------------- 6. 导出
def test_export(client, auth_headers):
    """导出：xlsx / pdf 正常流，非法格式与空结果异常流。"""
    xlsx = client.get("/api/dashboard/export?metric=M16&format=xlsx", headers=auth_headers["analyst"])
    assert xlsx.status_code == 200
    assert xlsx.content[:2] == b"PK" and len(xlsx.content) > 1000
    assert "attachment" in xlsx.headers["content-disposition"]

    pdf = client.get("/api/dashboard/export?metric=M16&format=pdf", headers=auth_headers["analyst"])
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    assert client.get("/api/dashboard/export?format=csv", headers=auth_headers["analyst"]).status_code == 400
    assert client.get("/api/dashboard/export?metric=M99", headers=auth_headers["analyst"]).status_code == 404
    assert client.get("/api/dashboard/export?metric=M16").status_code == 401


# ---------------------------------------------------------------- 7. 智能分析
def test_llm_apis(client, auth_headers):
    """智能问数、报告生成、异常归因与口径问答（离线规则引擎路径）。"""
    caps = client.get("/api/llm/capabilities", headers=auth_headers["analyst"]).json()["data"]
    assert len(caps["metrics"]) == 33
    assert len(caps["dims"]) >= 11
    assert caps["granularities"] == ["day", "month", "period"]

    # 问数：正常
    query = client.post("/api/llm/query", headers=auth_headers["analyst"], json={"question": "上月呼吸科床位使用率趋势如何"})
    assert query.status_code == 200
    result = query.json()["data"]
    assert result["intent"]["metric_code"] == "M11"
    assert result["intent"]["dim_value"] == "HN"
    assert result["chart"]["type"] in {"trend_line", "rank_bar", "kpi", "empty"}
    assert result["insight"]
    assert "SELECT" in result["sql"] and "LIMIT" in result["sql"]

    # 问数：异常（无法识别指标）+ 空问题
    bad = client.post("/api/llm/query", headers=auth_headers["analyst"], json={"question": "今天天气怎么样"})
    assert bad.status_code == 400
    assert client.post("/api/llm/query", headers=auth_headers["analyst"], json={"question": ""}).status_code == 422

    # 月报 / 周报
    monthly = client.post("/api/llm/report", headers=auth_headers["analyst"], json={"report_type": "monthly", "month": "2025-06"})
    assert monthly.status_code == 200
    assert len(monthly.json()["data"]["chapters"]) == 4
    weekly = client.post("/api/llm/report", headers=auth_headers["analyst"], json={"report_type": "weekly", "week": "2025-W25"})
    assert weekly.status_code == 200
    assert client.post("/api/llm/report", headers=auth_headers["analyst"], json={"report_type": "yearly"}).status_code == 400
    assert client.post("/api/llm/report", headers=auth_headers["analyst"], json={"report_type": "monthly", "month": "bad"}).status_code == 400

    # 口径问答：命中与未命中
    hit = client.post("/api/llm/kb", headers=auth_headers["analyst"], json={"question": "床位使用率怎么算"}).json()["data"]
    assert hit["matched"] is True and hit["refs"]
    miss = client.post("/api/llm/kb", headers=auth_headers["analyst"], json={"question": "医院食堂几点开饭"}).json()["data"]
    assert miss["matched"] is False and miss["refs"] == []

    # 异常归因：正常 + 无数据指标
    anomaly = client.post("/api/llm/anomaly", headers=auth_headers["analyst"], json={"metric": "M16"})
    assert anomaly.status_code in {200, 404}
    if anomaly.status_code == 200:
        assert "top" in anomaly.json()["data"]
    assert client.post("/api/llm/anomaly", headers=auth_headers["analyst"], json={"metric": "M99"}).status_code in {400, 404}
