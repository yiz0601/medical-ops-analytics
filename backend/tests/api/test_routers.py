"""接口测试（阶段四 · 步骤 3-4）。

    test_auth_flow           登录、建用户、鉴权与数据隔离回归
    test_dashboard_overview  驾驶舱接口结构与响应（含统一外壳、数据隔离）
    test_theme_metrics       各主题指标接口正常与异常分支、导出、任务与质量接口
"""

from __future__ import annotations

import json
from uuid import uuid4

from sqlalchemy import select


def _unique(name: str) -> str:
    return f"{name}_{uuid4().hex[:8]}"


# ---------------------------------------------------------------- 认证与权限
def test_auth_flow(client):
    """登录 -> 令牌 -> 访问受保护接口 -> 建用户 -> 越权/冲突分支。"""
    # 登录成功
    response = client.post("/api/auth/login", json={"username": "admin", "password": "Admin@123"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"] == 0 and body["msg"] == "success"
    token = body["data"]["access_token"]
    assert body["data"]["token_type"] == "bearer"
    assert body["data"]["user"]["role_code"] == "ADMIN"
    assert body["data"]["expires_in"] > 0

    headers = {"Authorization": f"Bearer {token}"}
    profile = client.get("/api/auth/profile", headers=headers)
    assert profile.status_code == 200
    assert profile.json()["data"]["username"] == "admin"

    # 密码错误 / 缺少令牌 / 伪造令牌
    assert client.post("/api/auth/login", json={"username": "admin", "password": "bad"}).status_code == 401
    assert client.get("/api/auth/profile").status_code == 401
    assert client.get("/api/auth/profile", headers={"Authorization": "Bearer not-a-token"}).status_code == 401
    bad_token = client.get("/api/auth/profile", headers={"Authorization": "Bearer not-a-token"}).json()
    assert bad_token["code"] == 40101

    # 科室用户登录（数据范围 = 本科室）
    dept_login = client.post("/api/auth/login", json={"username": "dept_hn", "password": "Dept@123"})
    assert dept_login.status_code == 200
    assert dept_login.json()["data"]["user"]["dept_code"] == "HN"

    # 管理员建用户
    new_username = _unique("doctor")
    created = client.post(
        "/api/auth/users",
        headers=headers,
        json={"username": new_username, "password": "Test@12345", "real_name": "测试医生",
              "role_code": "department", "dept_code": "EK"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["data"]["role_code"] == "DEPT_USER"

    new_login = client.post("/api/auth/login", json={"username": new_username, "password": "Test@12345"})
    assert new_login.status_code == 200

    # 重复账号 409
    duplicated = client.post(
        "/api/auth/users",
        headers=headers,
        json={"username": new_username, "password": "Test@12345", "role_code": "ANALYST"},
    )
    assert duplicated.status_code == 409
    assert duplicated.json()["code"] == 40901

    # 非管理员建用户 403
    analyst_login = client.post("/api/auth/login", json={"username": "analyst01", "password": "Analyst@123"})
    analyst_token = analyst_login.json()["data"]["access_token"]
    forbidden = client.post(
        "/api/auth/users",
        headers={"Authorization": f"Bearer {analyst_token}"},
        json={"username": _unique("x"), "password": "Test@12345", "role_code": "ANALYST"},
    )
    assert forbidden.status_code == 403

    # 参数校验分支：密码过短 / 科室用户缺 dept_code
    assert client.post(
        "/api/auth/users", headers=headers, json={"username": _unique("y"), "password": "short"}
    ).status_code == 422
    missing_dept = client.post(
        "/api/auth/users",
        headers=headers,
        json={"username": _unique("z"), "password": "Test@12345", "role_code": "DEPT_USER"},
    )
    assert missing_dept.status_code == 400
    assert missing_dept.json()["code"] == 40001

    # 用户列表（仅管理员）
    listing = client.get("/api/auth/users", headers=headers)
    assert listing.status_code == 200
    assert len(listing.json()["data"]) >= 4
    assert client.get("/api/auth/users", headers={"Authorization": f"Bearer {analyst_token}"}).status_code == 403


def test_audit_log_written(client, db_session):
    """审计日志：登录成功后写入 sys_audit_log（后台任务已同步执行）。"""
    from app.models.sys import SysAuditLog

    client.post("/api/auth/login", json={"username": "admin", "password": "Admin@123"})
    rows = db_session.execute(select(SysAuditLog).where(SysAuditLog.action == "login")).scalars().all()
    assert rows, "登录应写入审计日志"
    assert any(row.result == "OK" for row in rows)


# ---------------------------------------------------------------- 驾驶舱
def test_dashboard_overview(client, auth_headers):
    """驾驶舱总览：统一外壳、KPI/趋势/排行结构、数据隔离与异常分支。"""
    response = client.get("/api/dashboard/overview", headers=auth_headers["analyst"])
    assert response.status_code == 200, response.text
    payload = response.json()
    assert set(payload) == {"code", "msg", "data"}
    data = payload["data"]
    assert data["dept_scope"] == "ALL"
    assert len(data["kpis"]) >= 5
    assert data["kpis"][0]["metric_code"].startswith("M")
    assert data["trend"], "收入趋势不应为空"
    assert data["dept_rank"] and data["dept_rank"][0]["metric_code"] == "M16"
    assert "M27" in data["pending_metrics"]

    # 科室用户：仅本科室范围
    dept_view = client.get("/api/dashboard/overview", headers=auth_headers["department"])
    assert dept_view.status_code == 200
    assert dept_view.json()["data"]["dept_scope"] == "HN"

    # 未登录
    assert client.get("/api/dashboard/overview").status_code == 401

    # 非法粒度 -> 40001
    bad = client.get("/api/dashboard/overview?granularity=hour", headers=auth_headers["analyst"])
    assert bad.status_code == 400
    assert bad.json()["code"] == 40001

    # 健康检查与连通性（经统一外壳包装）
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["data"]["status"] == "up"
    assert client.get("/api/ping").json()["data"]["pong"] is True


def test_export_endpoints(client, auth_headers):
    """导出：xlsx 与 pdf 文件流，非法格式与空结果分支。"""
    xlsx = client.get("/api/dashboard/export?metric=M01&format=xlsx", headers=auth_headers["analyst"])
    assert xlsx.status_code == 200
    assert xlsx.content[:2] == b"PK"
    assert "attachment" in xlsx.headers["content-disposition"]

    pdf = client.get("/api/dashboard/export?metric=M01&format=pdf", headers=auth_headers["analyst"])
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")

    bad_format = client.get("/api/dashboard/export?format=csv", headers=auth_headers["analyst"])
    assert bad_format.status_code == 400
    assert bad_format.json()["code"] == 40001

    empty = client.get("/api/dashboard/export?metric=M99", headers=auth_headers["analyst"])
    assert empty.status_code == 404


# ---------------------------------------------------------------- 五大主题
def test_theme_metrics(client, auth_headers):
    """五大主题路由：默认指标、显式指标、下钻、异常分支与数据隔离。"""
    routes = {
        "outpatient": "M01",
        "inpatient": "M08",
        "revenue": "M16",
        "disease": "M24",
        "resource": "M11",
    }
    for route in routes:
        response = client.get(f"/api/{route}/metrics", headers=auth_headers["analyst"])
        assert response.status_code == 200, f"{route}: {response.text}"
        data = response.json()["data"]
        assert data["theme"] == route
        assert data["series"], f"{route} 应返回指标序列"
        assert data["granularity"] == "month"
        assert data["date_range"] == ["2025-04-01", "2025-06-30"]

    # 显式指标 + 维度 + 下钻
    custom = client.get(
        "/api/outpatient/metrics?metrics=M01,M16&dims=ALL&drill=month&granularity=period",
        headers=auth_headers["analyst"],
    )
    assert custom.status_code == 200
    payload = custom.json()["data"]
    assert payload["drill"] == "month"
    assert {item["metric_code"] for item in payload["series"]} == {"M01", "M16"}

    # 非法粒度 / 非法下钻
    assert client.get("/api/outpatient/metrics?granularity=week", headers=auth_headers["analyst"]).status_code == 400
    assert client.get("/api/outpatient/metrics?drill=unknown", headers=auth_headers["analyst"]).status_code == 400

    # 数据隔离：科室用户查询 ALL 维度时被过滤为本科室
    dept_view = client.get("/api/inpatient/metrics?dims=ALL,EK,HN", headers=auth_headers["department"])
    assert dept_view.status_code == 200
    dim_values = {point["dim_value"] for item in dept_view.json()["data"]["series"] for point in item["points"]}
    assert dim_values <= {"HN"}

    # 未登录 401
    assert client.get("/api/outpatient/metrics").status_code == 401


def test_task_and_quality_endpoints(client, auth_headers, tmp_path, monkeypatch):
    """任务状态、手动触发与质量报告（含报告缺失分支）。"""
    from app.services import task_service

    # 任务状态：无日志时全部 UNKNOWN
    monkeypatch.setattr(task_service, "task_log_path", lambda: tmp_path / "task_run.log")
    status = client.get("/api/task/status", headers=auth_headers["analyst"])
    assert status.status_code == 200
    assert status.json()["data"]["total"] == len(task_service.TASK_NAMES)
    assert status.json()["data"]["succeeded"] == 0

    # 写入一条日志后能看到成功状态
    (tmp_path / "task_run.log").write_text(
        json.dumps({"task_name": "extract_ods", "status": "SUCCESS", "rows": 59922, "cost_ms": 2100.0, "log_time": "2025-06-30 02:00:00"}) + "\n",
        encoding="utf-8",
    )
    refreshed = client.get("/api/task/status", headers=auth_headers["analyst"]).json()["data"]
    assert refreshed["succeeded"] == 1
    assert refreshed["tasks"][1]["task_name"] == "extract_ods"
    assert refreshed["tasks"][1]["rows"] == 59922

    # 手动触发：非管理员 403，管理员成功（执行器被替换为桩）
    payload = {"task_name": "extract_ods", "start_date": "2025-04-01", "end_date": "2025-06-30"}
    assert client.post("/api/task/trigger", json=payload, headers=auth_headers["analyst"]).status_code == 403

    monkeypatch.setitem(task_service.TASK_RUNNERS, "extract_ods", lambda start, end: {"ods": 100})
    triggered = client.post("/api/task/trigger", json=payload, headers=auth_headers["admin"])
    assert triggered.status_code == 200
    assert triggered.json()["data"]["rows"] == 100

    # 非白名单任务 400
    bad = client.post("/api/task/trigger", json={"task_name": "drop_all"}, headers=auth_headers["admin"])
    assert bad.status_code == 400

    # 质量报告：报告不存在 404
    monkeypatch.setattr(task_service, "_log_dir", lambda: tmp_path)
    assert client.get("/api/quality/report", headers=auth_headers["analyst"]).status_code == 404

    # 报告存在 200
    report = {
        "report_meta": {"batch_date": "2025-06-30", "generate_time": "2025-07-01 02:00:00"},
        "summary": {"total_rules": 25, "passed": 23, "warn": 2, "failed": 0, "score": 92.0,
                    "coverage_rate": 100.0, "blocking": False},
        "alerts": [{"rule_code": "QR-DQ-19", "rule_name": "行数波动率", "table": "ods_his_inpatient_visit",
                    "level": "WARN", "status": "WARN", "failed": 1, "detail": "6-30 出院 190 例"}],
    }
    (tmp_path / "quality_report_20250630.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    ok_report = client.get("/api/quality/report", headers=auth_headers["analyst"])
    assert ok_report.status_code == 200
    data = ok_report.json()["data"]
    assert data["score"] == 92.0 and data["total_rules"] == 25
    assert data["alerts"][0]["rule_code"] == "QR-DQ-19"

    # 科室用户无权查看质量报告 403
    assert client.get("/api/quality/report", headers=auth_headers["department"]).status_code == 403
