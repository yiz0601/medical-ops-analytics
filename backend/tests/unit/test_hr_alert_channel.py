"""人事系统人力数据源与质量告警通道的 ETL 侧单元测试。

覆盖任务书建设目标：
    目标 1「接入不少于 5 类数据源（含科室人力）」——hr_staff 源接入 ODS/DWD 并支撑 M28/M29
    目标 6「质检规则覆盖率 ≥95% / 告警通知及时率 100%」——28 条规则、字段覆盖率、站内信送达
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import delete, insert, select

from etl.config.alert_schema import sys_alert
from etl.config.baseline import DWD_EXPECTED_ROWS, ODS_EXPECTED_ROWS
from etl.config.dwd_schema import dwd_hr_staff_detail
from etl.config.ods_schema import ODS_TABLES
from etl.config.source_config import list_sources
from etl.jobs.alert_notify import list_alerts, publish_alerts, timeliness_stats
from etl.jobs.extract_ods import EXTRACTORS, extract_hr_staff


def test_hr_staff_registered_as_datasource():
    """人力源已在 sources.json 注册，且系统类型为 HR。"""
    sources = {item["source_name"]: item for item in list_sources()}
    assert "hr_staff" in sources
    assert sources["hr_staff"]["system_type"] == "HR"
    assert sources["hr_staff"]["target_table"] == "ods_hr_staff"
    # 任务书列举的 6 个数据对象均已注册（HIS 门诊 / HIS 住院 / EMR / LIS / 财务 / 人力）
    assert {"his_outpatient", "his_inpatient", "emr_record", "lis_report", "finance_excel", "hr_staff"} <= set(sources)


def test_hr_staff_ods_and_dwd_baseline():
    """ODS/DWD 人力表已纳入分层基线。"""
    assert ODS_TABLES["ods_hr_staff"] is not None
    assert ODS_EXPECTED_ROWS["ods_hr_staff"] == 30
    assert DWD_EXPECTED_ROWS["dwd_hr_staff_detail"] == 30
    assert "ods_hr_staff" in EXTRACTORS


def test_extract_hr_staff_rows_and_filter():
    """抽取人力台账：全期 30 行（10 科室 × 3 个月末快照），按 stat_date 过滤生效。"""
    frame = extract_hr_staff("2025-04-01", "2025-06-30")
    assert len(frame) == 30
    assert set(frame["dept_code"]) == {"HN", "HX", "SJ", "XH", "GK", "PW", "FC", "JZ", "EK", "ICU"}
    assert int(frame["doctor_cnt"].astype(int).sum()) == 123 * 3
    assert int(frame["nurse_cnt"].astype(int).sum()) == 217 * 3

    june = extract_hr_staff("2025-06-01", "2025-06-30")
    assert len(june) == 10
    assert set(june["stat_date"]) == {"2025-06-30"}


def test_staff_map_prefers_hr_ledger(seeded_engine):
    """指标人力取数优先人事台账（DWD），台账缺失时回退科室维表。"""
    from etl.config.dim_schema import dim_department
    from etl.jobs.ads_indicators import _staff_map

    # 维表维护值：HN 医师 12 / 护士 20（测试库无维表数据时先写入一行）
    with seeded_engine.begin() as conn:
        conn.execute(delete(dwd_hr_staff_detail))
        conn.execute(delete(dim_department).where(dim_department.c.dept_code == "HN"))
        conn.execute(
            insert(dim_department),
            [
                {
                    "dept_code": "HN",
                    "dept_name": "呼吸内科",
                    "parent_code": "NK",
                    "dept_level": 2,
                    "dept_type": "临床科室",
                    "org_area": "本部",
                    "bed_cnt": 18,
                    "doctor_cnt": 12,
                    "nurse_cnt": 20,
                    "is_active": 1,
                }
            ],
        )

    fallback = _staff_map(seeded_engine, "2025-06-30")
    assert fallback["HN"]["doctor_cnt"] == 12
    assert fallback["HN"]["nurse_cnt"] == 20

    # 写入台账并改值：取最新账期快照
    with seeded_engine.begin() as conn:
        conn.execute(
            insert(dwd_hr_staff_detail),
            [
                {
                    "dept_code": "HN",
                    "stat_date": date(2025, 6, 30),
                    "dept_name": "呼吸内科",
                    "dept_parent_code": "NK",
                    "dept_level": 2,
                    "doctor_cnt": 40,
                    "nurse_cnt": 60,
                    "staff_total": 100,
                    "stat_ym": "2025-06",
                    "etl_batch_date": date(2025, 6, 30),
                    "etl_batch_id": "B20250630",
                    "etl_load_time": date(2025, 6, 30),
                }
            ],
        )
    ledger = _staff_map(seeded_engine, "2025-06-30")
    assert ledger["HN"]["doctor_cnt"] == 40
    assert ledger["HN"]["nurse_cnt"] == 60
    # 台账只含 HN 时其他科室不在映射中（下游按 0 处理，避免误用旧值）
    assert "XH" not in ledger


def test_quality_rules_and_coverage():
    """28 条规则、关键字段覆盖率 100%（≥95% 达标）。"""
    from etl.jobs.quality_check import KEY_FIELDS, RECONCILE_PAIRS, _coverage

    total_rules = len(KEY_FIELDS) * 2 + 5 + 2 + len(RECONCILE_PAIRS)
    assert total_rules == 28
    coverage, covered, key_total = _coverage()
    assert coverage == 100.0
    assert covered == key_total == 32
    assert "ods_hr_staff" in KEY_FIELDS
    assert ("ods_hr_staff", "dwd_hr_staff_detail") in RECONCILE_PAIRS


def test_publish_alerts_writes_station_mail(seeded_engine):
    """告警写入站内信表并记录送达耗时，及时率 100%。"""
    alerts = [
        {"rule_code": "QR-DQ-20", "rule_name": "行数波动率", "table": "ods_his_outpatient_visit",
         "level": "WARN", "status": "WARN", "failed": 2, "detail": "波动超阈值"},
    ]
    summary = publish_alerts(alerts, batch_date="2025-06-30", engine=seeded_engine)
    assert summary["total"] == 1
    assert summary["delivered"] == 1
    assert summary["timeliness_rate"] == 100.0
    assert summary["channel"] == "站内信"

    rows = list_alerts(batch_date="2025-06-30", engine=seeded_engine, limit=5)
    assert len(rows) == 1
    assert rows[0]["alert_no"] == "AL20250630-001"
    assert rows[0]["notified_at"] is not None
    assert rows[0]["notify_ms"] == 0
    assert rows[0]["is_read"] == 0

    stats = timeliness_stats(batch_date="2025-06-30", engine=seeded_engine)
    assert stats["total"] == 1
    assert stats["timely"] == 1
    assert stats["unread"] == 1


def test_quality_blocked_error_raised(monkeypatch, seeded_engine):
    """BLOCK 级规则失败时按 raise_on_block 抛出阻断异常（阻断下游发布）。"""
    from etl.jobs import quality_check

    blocking_result = {
        "rule_code": "QR-REC-01",
        "rule_name": "ODS-DWD 行数对账",
        "rule_type": "一致性",
        "table": "ods_his_outpatient_visit→dwd_outpatient_visit_detail",
        "level": "BLOCK",
        "total": 9000,
        "failed": 5,
        "pass_rate": 99.94,
        "status": "FAIL",
        "detail": "差异 5 行",
    }
    monkeypatch.setattr(quality_check, "run_all_rules", lambda *a, **k: [blocking_result])

    with pytest.raises(quality_check.QualityBlockedError) as excinfo:
        quality_check.generate_quality_report("2025-06-30", engine=seeded_engine, notify=False, raise_on_block=True)
    assert excinfo.value.blocking_alerts

    # 不开启阻断时仅记录告警、异常不外抛
    report = quality_check.generate_quality_report("2025-06-30", engine=seeded_engine, notify=False)
    assert report["summary"]["blocking"] is True
