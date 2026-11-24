"""科室运营看板与质量告警站内信接口测试（任务书建设目标 3 / 6 补充）。

    GET  /api/dashboard/dept                 科室运营看板（单科室全指标 + 名次 + 人力快照）
    GET  /api/system/alerts                  告警列表 + 未读数 + 及时率
    GET  /api/system/alerts/timeliness       告警通知及时率统计
    POST /api/system/alerts/{id}/read        单条已读
    POST /api/system/alerts/read-all         全部已读
"""

from __future__ import annotations

from etl.jobs.alert_notify import publish_alerts

ALERTS = [
    {
        "rule_code": "QR-DQ-19",
        "rule_name": "行数波动率",
        "table": "ods_his_inpatient_visit",
        "level": "WARN",
        "status": "WARN",
        "failed": 36,
        "detail": "2025-06-30 出院 190 例，环比 +1166.7%",
    },
    {
        "rule_code": "QR-REC-03",
        "rule_name": "ODS-DWD 行数对账",
        "table": "ods_his_charge_detail→dwd_charge_detail",
        "level": "BLOCK",
        "status": "FAIL",
        "failed": 12,
        "detail": "ODS 44078 行 / DWD 44066 行，差异 12 行",
    },
]


def test_dept_board_ok(client, auth_headers):
    """管理员查询科室看板：返回科室信息、KPI、趋势与名次字段。"""
    resp = client.get("/api/dashboard/dept", params={"dept": "HN"}, headers=auth_headers["admin"])
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["dept_code"] == "HN"
    assert data["dept_name"] == "呼吸内科"
    assert data["period"] == ["2025-04-01", "2025-06-30"]
    codes = {item["metric_code"] for item in data["kpis"]}
    assert {"M01", "M08", "M11", "M12", "M16"} <= codes
    assert data["trends"], "应返回趋势序列"
    assert data["staff"]["source"].startswith("HR")
    assert isinstance(data["pending_metrics"], list)


def test_dept_board_requires_dept(client, auth_headers):
    """未指定科室（ALL）时返回参数错误。"""
    resp = client.get("/api/dashboard/dept", params={"dept": "ALL"}, headers=auth_headers["admin"])
    assert resp.status_code == 400
    assert "科室" in resp.json()["msg"]


def test_dept_board_dept_user_scope(client, auth_headers):
    """科室用户只能查看本科室，跨科室返回 403。"""
    own = client.get("/api/dashboard/dept", params={"dept": "HN"}, headers=auth_headers["department"])
    assert own.status_code == 200
    assert own.json()["data"]["dept_code"] == "HN"

    cross = client.get("/api/dashboard/dept", params={"dept": "XH"}, headers=auth_headers["department"])
    assert cross.status_code == 403
    assert "无权" in cross.json()["msg"]


def test_dept_board_default_dept_for_scoped_user(client, auth_headers):
    """科室用户不传 dept 时默认本科室。"""
    resp = client.get("/api/dashboard/dept", headers=auth_headers["department"])
    assert resp.status_code == 200
    assert resp.json()["data"]["dept_code"] == "HN"


def test_alert_station_flow(client, seeded_engine, auth_headers):
    """告警站内信：推送 → 列表/未读/及时率 → 单条已读 → 全部已读。"""
    publish_alerts(ALERTS, batch_date="2025-06-30", engine=seeded_engine)

    resp = client.get("/api/system/alerts", params={"limit": 10}, headers=auth_headers["analyst"])
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["unread"] == 2
    assert len(data["items"]) == 2
    assert data["timeliness"]["timeliness_rate"] == 100.0
    assert data["timeliness"]["channels"] == ["站内信"]
    levels = {item["level"] for item in data["items"]}
    assert levels == {"WARN", "BLOCK"}

    first_id = data["items"][0]["id"]
    resp = client.post(f"/api/system/alerts/{first_id}/read", headers=auth_headers["analyst"])
    assert resp.status_code == 200
    assert resp.json()["data"]["affected"] == 1

    resp = client.get("/api/system/alerts", params={"unread_only": True}, headers=auth_headers["analyst"])
    assert resp.json()["data"]["unread"] == 1

    resp = client.post("/api/system/alerts/read-all", headers=auth_headers["analyst"])
    assert resp.status_code == 200
    assert resp.json()["data"]["affected"] >= 1

    resp = client.get("/api/system/alerts/timeliness", headers=auth_headers["admin"])
    assert resp.status_code == 200
    stats = resp.json()["data"]
    assert stats["total"] == 2
    assert stats["timely"] == 2
    assert stats["timeliness_rate"] == 100.0
    assert stats["threshold_seconds"] == 300


def test_alert_station_requires_login(client):
    """未登录访问告警接口返回 401。"""
    assert client.get("/api/system/alerts").status_code == 401


def test_alerts_idempotent_publish(seeded_engine):
    """同批次重复推送告警为幂等（先删后插，不堆积）。"""
    batch = "2025-06-30"
    publish_alerts(ALERTS, batch_date=batch, engine=seeded_engine)
    publish_alerts(ALERTS, batch_date=batch, engine=seeded_engine)

    from etl.config.alert_schema import sys_alert
    from sqlalchemy import func, select

    with seeded_engine.connect() as conn:
        total = conn.execute(select(func.count()).select_from(sys_alert)).scalar_one()
    assert int(total) == len(ALERTS)
