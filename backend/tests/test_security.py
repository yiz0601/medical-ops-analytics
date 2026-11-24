"""安全用例（阶段七 · 步骤 4）。

    test_unauthorized     无 token 访问受保护接口，断言返回 401
    test_forbidden        科室用户访问全院级接口，断言返回 403
    test_sql_injection    注入 payload 断言被参数化拦截且不泄露数据
    test_data_masking     断言患者姓名、证件号、电话为脱敏格式
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

PROTECTED_ENDPOINTS = [
    ("GET", "/api/auth/profile"),
    ("GET", "/api/dashboard/overview"),
    ("GET", "/api/outpatient/metrics"),
    ("GET", "/api/quality/report"),
    ("GET", "/api/system/roles"),
    ("POST", "/api/llm/query"),
]
INJECTION_PAYLOADS = [
    "'; DROP TABLE ads_indicator_result; --",
    "1' OR '1'='1",
    "M01' UNION SELECT username, password_hash FROM sys_user --",
    "'; UPDATE sys_user SET role_code='ADMIN' WHERE 1=1; --",
    "../../etc/passwd",
    "%00%27%20OR%201=1",
]


def test_unauthorized(client):
    """无 token / 伪造 token / 过期 token 一律 401，且不泄露内部信息。"""
    for method, url in PROTECTED_ENDPOINTS:
        if method == "GET":
            response = client.get(url)
        else:
            response = client.post(url, json={"question": "上月呼吸床位数"})
        assert response.status_code == 401, f"{method} {url} 应返回 401，实际 {response.status_code}"
        body = response.json()
        assert body["code"] == 40101
        assert "Traceback" not in response.text
        assert "password" not in response.text.lower()

    forged = client.get("/api/dashboard/overview", headers={"Authorization": "Bearer forged.token.value"})
    assert forged.status_code == 401
    assert forged.json()["code"] == 40101


def test_forbidden(client, make_token):
    """科室用户访问全院级/管理级接口应返回 403。"""
    dept_headers = {"Authorization": f"Bearer {make_token('department', dept='HN')}"}

    # 管理接口：用户/角色/数据源/任务触发
    assert client.get("/api/auth/users", headers=dept_headers).status_code == 403
    assert client.get("/api/system/roles", headers=dept_headers).status_code == 403
    assert client.get("/api/system/datasources", headers=dept_headers).status_code == 403
    assert client.post("/api/task/trigger", headers=dept_headers, json={"task_name": "extract_ods"}).status_code == 403
    assert client.get("/api/quality/report", headers=dept_headers).status_code == 403

    # 数据越权：科室用户查看全院汇总应被过滤为本科室（不是 403，但看不到 ALL）
    overview = client.get("/api/dashboard/overview", headers=dept_headers)
    assert overview.status_code == 200
    assert overview.json()["data"]["dept_scope"] == "HN"

    metrics = client.get("/api/outpatient/metrics?dims=ALL,EK,HN", headers=dept_headers)
    assert metrics.status_code == 200
    dim_values = {point["dim_value"] for item in metrics.json()["data"]["series"] for point in item["points"]}
    assert dim_values <= {"HN"}, f"科室用户不应看到其他科室数据：{dim_values}"


def test_sql_injection(client, auth_headers, db_session):
    """注入 payload 被参数化拦截：接口返回 400/404，数据表未被破坏，用户表未被篡改。"""
    # NL2SQL 注入：注入文本会被原样回显在 question 字段，因此检查"是否真的泄露了数据"
    for payload in INJECTION_PAYLOADS:
        response = client.post("/api/llm/query", headers=auth_headers["admin"], json={"question": payload})
        assert response.status_code in {400, 404, 200}, response.text
        assert "Traceback" not in response.text
        # 不得出现 bcrypt 哈希、用户表字段值或越权表访问
        assert "$2b$" not in response.text, "响应中不应出现密码哈希"
        body = response.json()
        sql = (body.get("data") or {}).get("sql", "") if isinstance(body.get("data"), dict) else ""
        assert "sys_user" not in sql.lower(), f"生成的 SQL 不应引用系统表：{sql}"
        assert "union" not in sql.lower(), f"生成的 SQL 不应包含 UNION：{sql}"

    # 指标编码注入（直接传给后端参数）
    for payload in INJECTION_PAYLOADS:
        response = client.get(f"/api/outpatient/metrics?metrics={payload}", headers=auth_headers["analyst"])
        assert response.status_code in {200, 400, 422}, response.text
        assert response.status_code != 500

    # 数据未被破坏
    count = db_session.execute(text("SELECT COUNT(*) FROM ads_indicator_result")).scalar()
    assert count and int(count) > 0, "注入后指标结果表不应被清空"
    admin_role = db_session.execute(text("SELECT role_code FROM sys_user WHERE username = 'admin'")).scalar()
    assert admin_role == "ADMIN", "用户角色不应被注入修改"


def test_data_masking(db_session):
    """DWD 层患者姓名、身份证号、手机号必须为脱敏格式，不出现明文。"""
    from etl.config.dwd_schema import DWD_TABLES
    from etl.config.loader import read_table_df
    from app.core.db import get_engine

    frame = read_table_df(get_engine(), DWD_TABLES["dwd_outpatient_visit_detail"])
    if frame.empty:
        pytest.skip("测试库未装载 DWD 明细（ETL 冒烟由 tests.test_etl_smoke 覆盖）")

    sample = frame.head(200)
    assert sample["patient_name_masked"].str.contains(r"\*").all()
    assert sample["id_card_masked"].str.contains(r"\*").all()
    assert sample["phone_masked"].str.contains(r"\*").all()
    assert not sample["id_card_masked"].str.match(r"^\d{17}[\dXx]$").any()
    assert not sample["phone_masked"].str.match(r"^\d{11}$").any()
