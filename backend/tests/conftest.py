"""pytest 公共夹具（阶段四 · 步骤 3-2）。

    seeded_engine   会话级：临时 SQLite 库 + ETL 全层建表 + 应用系统表 + 指标结果样例数据
    db_session      函数级：带 SAVEPOINT 事务回滚隔离的 ORM 会话
    client          函数级：TestClient（覆盖 get_session 依赖指向测试库）
    make_token      函数级：按角色签发测试令牌（admin / analyst / department）
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# ---------------------------------------------------------------------------
# 必须在导入 app / etl 之前固定测试库与密钥，避免触碰开发库
# ---------------------------------------------------------------------------
_TEST_DIR = Path(tempfile.mkdtemp(prefix="moa_api_test_"))
os.environ["MOA_DB_URL"] = f"sqlite:///{(_TEST_DIR / 'test.db').as_posix()}"
os.environ["MOA_JWT_SECRET"] = "test-secret-for-pytest"
os.environ["MOA_APP_ENV"] = "test"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, insert  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

BATCH_DATE = "2025-06-30"
PERIOD = ("2025-04-01", "2025-06-30")
MONTH_ENDS = ["2025-04-30", "2025-05-31", "2025-06-30"]

# 样例指标值（M01/M08/M11/M12/M16/M19/M24 + 一个 PENDING 指标 M27）
_SAMPLE_VALUES: dict[str, tuple[float, str, str]] = {
    "M01": (9000.0, "人次", "门诊"),
    "M08": (1500.0, "人次", "住院"),
    "M11": (88.89, "%", "住院"),
    "M12": (9.54, "天", "住院"),
    "M16": (44260283.80, "元", "收入"),
    "M19": (30.0, "%", "收入"),
    "M24": (1.09, "指数", "病种"),
}


def _seed_ads_data(engine) -> None:
    """写入指标结果样例数据（全院 ALL + 两个科室，月粒度三行 + 全期一行）。"""
    from etl.config.mart_schema import ads_indicator_result

    rows: list[dict[str, object]] = []
    dept_values = {"ALL": 1.0, "EK": 0.1, "HN": 0.12}
    for metric, (value, unit, theme) in _SAMPLE_VALUES.items():
        for dim_value, ratio in dept_values.items():
            for idx, stat_date in enumerate(MONTH_ENDS):
                month_value = round(value * ratio * (0.9 + 0.1 * idx), 4)
                rows.append(
                    {
                        "metric_code": metric,
                        "dim_value": dim_value,
                        "granularity": "month",
                        "stat_date": date.fromisoformat(stat_date),
                        "metric_name": f"指标{metric}",
                        "theme": theme,
                        "metric_value": month_value,
                        "unit": unit,
                        "data_status": "OK",
                        "metric_version": "V1.0",
                        "calc_batch_id": "B20250630",
                    }
                )
            rows.append(
                {
                    "metric_code": metric,
                    "dim_value": dim_value,
                    "granularity": "period",
                    "stat_date": date.fromisoformat("2025-06-30"),
                    "metric_name": f"指标{metric}",
                    "theme": theme,
                    "metric_value": round(value * ratio, 4),
                    "unit": unit,
                    "data_status": "OK",
                    "metric_version": "V1.0",
                    "calc_batch_id": "B20250630",
                }
            )
    # 数据源待补充指标（PENDING）：月粒度 + 全期
    for dim_value, ratio in dept_values.items():
        for granularity in ("month", "period"):
            rows.append(
                {
                    "metric_code": "M27",
                    "dim_value": dim_value,
                    "granularity": granularity,
                    "stat_date": date.fromisoformat("2025-06-30"),
                    "metric_name": "低风险组死亡率",
                    "theme": "病种",
                    "metric_value": None,
                    "unit": "%",
                    "data_status": "PENDING",
                    "metric_version": "V1.0",
                    "calc_batch_id": "B20250630",
                }
            )

    with engine.begin() as conn:
        conn.execute(delete(ads_indicator_result))
        conn.execute(insert(ads_indicator_result), rows)

    # 脱敏样例：供 tests/test_security.py::test_data_masking 校验（DWD 层不得出现明文）
    from etl.config.dwd_schema import DWD_TABLES

    masked_rows = [
        {
            "visit_id": f"OV90000{index}",
            "patient_id": f"P9000{index}",
            "patient_name_masked": "张**",
            "id_card_masked": "110184*******7609",
            "phone_masked": "138****7907",
            "gender": "女",
            "age": 40 + index,
            "age_group": "中年",
            "dept_code": "HN",
            "dept_name": "呼吸内科",
            "visit_date": date.fromisoformat("2025-05-1" + str(index)),
            "visit_ym": "2025-05",
            "visit_type": "普通",
            "visit_type_code": "PT",
            "fee_amount": 300.0 + index,
            "etl_batch_date": date.fromisoformat(BATCH_DATE),
            "etl_batch_id": "B20250630",
            "etl_load_time": __import__("datetime").datetime(2025, 6, 30, 2, 0, 0),
        }
        for index in range(1, 3)
    ]
    with engine.begin() as conn:
        conn.execute(delete(DWD_TABLES["dwd_outpatient_visit_detail"]))
        conn.execute(insert(DWD_TABLES["dwd_outpatient_visit_detail"]), masked_rows)


@pytest.fixture(scope="session")
def seeded_engine():
    """会话级测试库：建全部表 + 系统账号 + 指标结果样例数据。"""
    from app.core.db import ensure_schema, get_engine
    from etl.config.settings import init_ods_dwd_tables

    init_ods_dwd_tables()  # DIM/ODS/DWD/DWS/ADS 全部表（SQLite）
    engine = get_engine()
    ensure_schema(engine)  # sys_user / sys_audit_log + 默认账号
    _seed_ads_data(engine)
    return engine


@pytest.fixture()
def db_session(seeded_engine) -> Session:
    """函数级 ORM 会话：SAVEPOINT 隔离，测试结束自动回滚。"""
    connection = seeded_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(
        bind=connection, expire_on_commit=False, future=True, join_transaction_mode="create_savepoint"
    )()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def client(seeded_engine) -> TestClient:
    """TestClient：把 get_session 依赖覆盖为测试库会话。"""
    from app.core.db import get_session
    from app.main import create_app

    app = create_app()

    def _override_session():
        session = sessionmaker(bind=seeded_engine, expire_on_commit=False, future=True)()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = _override_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def make_token():
    """按角色签发测试令牌：make_token("admin") / make_token("department", dept="HN")。"""
    from app.core.security import create_access_token

    # 与 init_dim / ensure_schema 初始化的账号保持一致（dept_hn 为呼吸内科科室用户）
    names = {
        "admin": ("admin", "ADMIN", None),
        "analyst": ("analyst01", "ANALYST", None),
        "department": ("dept_hn", "DEPT_USER", "HN"),
    }
    counter = {"n": 0}

    def _factory(role: str = "analyst", dept: str | None = None) -> str:
        counter["n"] += 1
        username, role_code, dept_code = names.get(role, ("dept_hn", "DEPT_USER", dept or "HN"))
        if dept:
            dept_code = dept
        return create_access_token(
            {
                "username": username,
                "user_id": counter["n"],
                "role_code": role_code,
                "dept_code": dept_code,
            }
        )

    return _factory


@pytest.fixture()
def auth_headers(make_token):
    """常用请求头：admin / analyst / department 三种角色。"""
    return {
        "admin": {"Authorization": f"Bearer {make_token('admin')}"},
        "analyst": {"Authorization": f"Bearer {make_token('analyst')}"},
        "department": {"Authorization": f"Bearer {make_token('department', dept='HN')}"},
    }
