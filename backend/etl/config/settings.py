"""ETL 全局配置：目录路径、数据库连接、批次与统计期约定。

数据库连接优先级：
    1. MOA_DB_URL / DB_URL 环境变量（完整 SQLAlchemy URL）
    2. DB_HOST + DB_USER + ... 等分项环境变量（拼 MySQL URL）
    3. 缺省回退到 SQLite 文件库 backend/etl/logs/moa_dev.db
       —— 仅用于本地无 MySQL 时的冒烟验证，生产必须提供 MySQL 连接。
"""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

# ---------------------------------------------------------------- 路径
ETL_DIR = Path(__file__).resolve().parent.parent            # backend/etl
BACKEND_DIR = ETL_DIR.parent                                # backend
PROJECT_ROOT = BACKEND_DIR.parent                           # 工程根目录
DATA_DIR = Path(os.getenv("MOA_DATA_DIR", PROJECT_ROOT / "data"))
MOCK_HIS_DIR = DATA_DIR / "mock_his"
FILES_DIR = DATA_DIR / "files"
LOG_DIR = Path(os.getenv("MOA_ETL_LOG_DIR", ETL_DIR / "logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)
SOURCES_FILE = ETL_DIR / "config" / "sources.json"
TASK_LOG_FILE = LOG_DIR / "task_run.log"

# ---------------------------------------------------------------- 批次与统计期
# 数据集统计窗：2025-04-01 ~ 2025-06-30，T+1 日终批，批次日期取跑批当日的业务日期
STAT_PERIOD_START = os.getenv("MOA_STAT_START", "2025-04-01")
STAT_PERIOD_END = os.getenv("MOA_STAT_END", "2025-06-30")
DEFAULT_BATCH_DATE = os.getenv("MOA_BATCH_DATE", STAT_PERIOD_END)

# ---------------------------------------------------------------- 质量阈值
VOLUME_WAVE_THRESHOLD = float(os.getenv("MOA_VOLUME_WAVE_THRESHOLD", "0.30"))
NULL_RATIO_THRESHOLD = float(os.getenv("MOA_NULL_RATIO_THRESHOLD", "0.01"))
RECONCILE_TOLERANCE = float(os.getenv("MOA_RECONCILE_TOLERANCE", "0.001"))

# ---------------------------------------------------------------- 数据库
_DEFAULT_SQLITE = LOG_DIR / "moa_dev.db"


def get_db_url() -> str:
    """解析数据库连接串（见模块 docstring 的优先级）。"""
    url = os.getenv("MOA_DB_URL") or os.getenv("DB_URL")
    if url:
        return url
    host = os.getenv("DB_HOST")
    if host:
        user = os.getenv("DB_USER", "moa")
        password = os.getenv("DB_PASSWORD", "")
        port = os.getenv("DB_PORT", "3306")
        name = os.getenv("DB_NAME", "medical_ops")
        return f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}?charset=utf8mb4"
    return f"sqlite:///{_DEFAULT_SQLITE.as_posix()}"


_ENGINE: Engine | None = None


def get_engine(echo: bool = False) -> Engine:
    """获取（缓存的）数据库引擎。"""
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = create_engine(get_db_url(), echo=echo, future=True, pool_pre_ping=True)
    return _ENGINE


def reset_engine() -> None:
    """释放缓存引擎（测试或切换连接串后调用）。"""
    global _ENGINE
    if _ENGINE is not None:
        _ENGINE.dispose()
        _ENGINE = None


def init_ods_dwd_tables(engine: Engine | None = None) -> list[str]:
    """建表（幂等）：在目标库中创建 DIM / ODS / DWD / DWS / ADS 全部表。

    生产环境应执行 sql/{dim,ods,dwd,dws,ads}/*.sql（MySQL DDL），
    本函数用于本地 SQLite 冒烟验证与单元测试，两者列定义保持一致。
    """
    from etl.config.dim_schema import DIM_METADATA
    from etl.config.dwd_schema import DWD_METADATA
    from etl.config.mart_schema import MART_METADATA
    from etl.config.ods_schema import ODS_METADATA

    eng = engine or get_engine()
    DIM_METADATA.create_all(eng, checkfirst=True)
    ODS_METADATA.create_all(eng, checkfirst=True)
    DWD_METADATA.create_all(eng, checkfirst=True)
    MART_METADATA.create_all(eng, checkfirst=True)
    return (
        sorted(DIM_METADATA.tables)
        + sorted(ODS_METADATA.tables)
        + sorted(DWD_METADATA.tables)
        + sorted(MART_METADATA.tables)
    )


def ping_db(engine: Engine | None = None) -> bool:
    """连通性检查。"""
    try:
        with (engine or get_engine()).connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001 - 探测型调用，任何异常都视为不可用
        return False


# ---------------------------------------------------------------- 批次工具
def normalize_batch_date(value: str | date | datetime | None = None) -> date:
    """把多种输入规整为 date（缺省取 DEFAULT_BATCH_DATE）。"""
    if value is None or value == "":
        value = DEFAULT_BATCH_DATE
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def batch_id_of(batch_date: date) -> str:
    """批次标识：B + yyyyMMdd（与 DWD/ADS 的 etl_batch_id 同源）。"""
    return f"B{batch_date:%Y%m%d}"
