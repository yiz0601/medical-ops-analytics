"""数据源接入与注册（阶段二 · 步骤 2）。

对外提供三个函数：
    register_source(name, conn_info)   注册/更新一个数据源配置
    test_connection(name)              测试数据源可用性（CSV 校验文件与表头，数据库试连）
    list_sources()                     返回已注册数据源清单

配置持久化在 backend/etl/config/sources.json；首次调用时用内置的 5 类数据源
（HIS 门诊/住院/收费、EMR、LIS、财务文件）自动初始化，与 data/ 目录一一对应。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from etl.config.ods_schema import ODS_SOURCE_COLUMNS
from etl.config.settings import PROJECT_ROOT, SOURCES_FILE

# ---------------------------------------------------------------- 内置默认数据源
# 5 类数据源：HIS（3 张表）、EMR、LIS、财务文件；全部以 CSV 落地，便于离线复现
DEFAULT_SOURCES: dict[str, dict[str, Any]] = {
    "his_outpatient": {
        "source_name": "his_outpatient",
        "source_type": "csv",
        "system_type": "HIS",
        "location": "data/mock_his/his_outpatient.csv",
        "target_table": "ods_his_outpatient_visit",
        "load_mode": "FULL",
        "cron": "0 2 * * *",
        "enabled": True,
        "remark": "HIS 门诊挂号就诊数据，T+1 日终批全量抽取",
    },
    "his_inpatient": {
        "source_name": "his_inpatient",
        "source_type": "csv",
        "system_type": "HIS",
        "location": "data/mock_his/his_inpatient.csv",
        "target_table": "ods_his_inpatient_visit",
        "load_mode": "FULL",
        "cron": "0 2 * * *",
        "enabled": True,
        "remark": "HIS 住院入出院数据，T+1 日终批全量抽取",
    },
    "his_charge": {
        "source_name": "his_charge",
        "source_type": "csv",
        "system_type": "HIS",
        "location": "data/mock_his/his_charge.csv",
        "target_table": "ods_his_charge_detail",
        "load_mode": "INC",
        "cron": "0 2 * * *",
        "enabled": True,
        "remark": "HIS 收费明细流水，按 fee_date 增量抽取，关键指标支持小时增量",
    },
    "emr_record": {
        "source_name": "emr_record",
        "source_type": "csv",
        "system_type": "EMR",
        "location": "data/mock_his/emr_record.csv",
        "target_table": "ods_emr_record",
        "load_mode": "FULL",
        "cron": "0 2 * * *",
        "enabled": True,
        "remark": "EMR 电子病历首页摘要，T+1 日终批",
    },
    "lis_report": {
        "source_name": "lis_report",
        "source_type": "csv",
        "system_type": "LIS",
        "location": "data/mock_his/lis_report.csv",
        "target_table": "ods_lis_report",
        "load_mode": "INC",
        "cron": "0 2 * * *",
        "enabled": True,
        "remark": "LIS 检验报告，按 report_date 增量抽取",
    },
    "finance_excel": {
        "source_name": "finance_excel",
        "source_type": "csv",
        "system_type": "FINANCE",
        "location": "data/files/finance_excel.csv",
        "target_table": "ods_finance_excel",
        "load_mode": "FULL",
        "cron": "0 3 * * *",
        "enabled": True,
        "remark": "财务日报（Excel/CSV 文件通道），人工上传或目录扫描",
    },
}

_VALID_TYPES = {"csv", "excel", "mysql", "oracle", "sqlserver", "api"}


# ---------------------------------------------------------------- 配置读写
def load_sources(force_default: bool = False) -> dict[str, dict[str, Any]]:
    """读取数据源配置；文件不存在时写入内置默认配置。"""
    if force_default or not SOURCES_FILE.exists():
        save_sources(DEFAULT_SOURCES)
        return {k: dict(v) for k, v in DEFAULT_SOURCES.items()}
    with SOURCES_FILE.open("r", encoding="utf-8") as fp:
        data = json.load(fp)
    sources = data.get("sources", data)
    return {k: dict(v) for k, v in sources.items()}


def save_sources(sources: dict[str, dict[str, Any]]) -> None:
    """写回数据源配置（保持人可读的缩进格式）。"""
    SOURCES_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "sources": sources}
    with SOURCES_FILE.open("w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)


def get_source(name: str) -> dict[str, Any]:
    """按名称取单个数据源配置，不存在时抛 KeyError。"""
    sources = load_sources()
    if name not in sources:
        raise KeyError(f"数据源未注册：{name}，已注册：{', '.join(sorted(sources))}")
    return sources[name]


def resolve_location(source: dict[str, Any]) -> Path:
    """把 source['location'] 解析为绝对路径（相对路径基于工程根目录）。"""
    location = source.get("location") or source.get("path") or ""
    path = Path(location)
    return path if path.is_absolute() else (PROJECT_ROOT / path)


# ---------------------------------------------------------------- 步骤 2 的三个能力
def register_source(
    name: str,
    conn_info: dict[str, Any],
    *,
    target_table: str | None = None,
    system_type: str | None = None,
    load_mode: str | None = None,
    cron: str | None = None,
    remark: str | None = None,
    overwrite: bool = True,
) -> dict[str, Any]:
    """注册（或更新）数据源连接信息。

    参数
    ----
    name        数据源名称，如 his_outpatient
    conn_info   连接信息：文件类传 {"source_type": "csv"|"excel", "location": "data/..."}；
                数据库类传 {"source_type": "mysql", "host": ..., "port": ...,
                "database": ..., "username": ..., "password_env": "HIS_DB_PASSWORD"}
    overwrite   已存在时是否覆盖（默认覆盖）

    返回注册后的完整配置记录。
    """
    if not name or not name.strip():
        raise ValueError("数据源名称不能为空")
    sources = load_sources()
    if name in sources and not overwrite:
        raise ValueError(f"数据源已存在：{name}（如需更新请传 overwrite=True）")

    info = dict(conn_info or {})
    source_type = str(info.get("source_type") or info.get("type") or "").lower()
    if source_type not in _VALID_TYPES:
        raise ValueError(f"不支持的数据源类型：{source_type or '(空)'}，可选 {sorted(_VALID_TYPES)}")

    record: dict[str, Any] = dict(sources.get(name, {}))
    record.update(
        {
            "source_name": name,
            "source_type": source_type,
            "system_type": system_type or record.get("system_type") or source_type.upper(),
            "enabled": bool(info.get("enabled", record.get("enabled", True))),
            "remark": remark or record.get("remark", ""),
        }
    )

    if source_type in {"csv", "excel"}:
        location = info.get("location") or info.get("path")
        if not location:
            raise ValueError("文件类数据源必须提供 location（相对工程根目录的文件路径）")
        record["location"] = str(location)
        record.pop("password", None)
    else:
        for key in ("host", "port", "database", "username"):
            if info.get(key) is not None:
                record[key] = info[key]
        if not record.get("host"):
            raise ValueError("数据库类数据源必须提供 host")
        # 口令只记录环境变量名，避免明文落盘
        if info.get("password_env"):
            record["password_env"] = info["password_env"]
        record.pop("password", None)

    if target_table:
        record["target_table"] = target_table
    if load_mode:
        record["load_mode"] = load_mode.upper()
    if cron:
        record["cron"] = cron

    sources[name] = record
    save_sources(sources)
    return record


def test_connection(name: str) -> bool:
    """测试数据源可用性。

    * 文件类（csv/excel）：文件存在、可读、表头与 ODS 目标表所需列一致
    * 数据库类：用 SQLAlchemy 试连并执行 SELECT 1（口令取 password_env 指向的环境变量）
    """
    source = get_source(name)
    source_type = source.get("source_type", "csv")

    if source_type in {"csv", "excel"}:
        path = resolve_location(source)
        if not path.exists() or not path.is_file():
            print(f"[FAIL] {name}: 文件不存在 -> {path}")
            return False
        try:
            # 源文件可能带 UTF-8 BOM，统一用 utf-8-sig 读取避免首列名出现 \ufeff
            with path.open("r", encoding="utf-8-sig") as fp:
                header = fp.readline().strip().split(",")
        except OSError as exc:
            print(f"[FAIL] {name}: 文件不可读 -> {exc}")
            return False
        expected = ODS_SOURCE_COLUMNS.get(source.get("target_table", ""), [])
        missing = [c for c in expected if c not in header]
        if missing:
            print(f"[FAIL] {name}: 表头缺少字段 -> {missing}")
            return False
        print(f"[OK]   {name}: 文件可读，{len(header)} 列，路径 {path}")
        return True

    # 数据库类数据源
    import os

    from sqlalchemy import create_engine, text

    try:
        password = os.getenv(source.get("password_env", ""), "") if source.get("password_env") else ""
        driver = {"mysql": "mysql+pymysql", "oracle": "oracle+cx_oracle", "sqlserver": "mssql+pymssql"}.get(
            source_type, "mysql+pymysql"
        )
        url = (
            f"{driver}://{source.get('username', '')}:{password}"
            f"@{source.get('host')}:{source.get('port', 3306)}/{source.get('database', '')}"
        )
        engine = create_engine(url, connect_args={"connect_timeout": 5}, future=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        print(f"[OK]   {name}: 数据库连接成功 -> {source.get('host')}:{source.get('port')}")
        return True
    except Exception as exc:  # noqa: BLE001 - 探测型调用
        print(f"[FAIL] {name}: 数据库连接失败 -> {exc}")
        return False


def list_sources() -> list[dict[str, Any]]:
    """返回已注册数据源清单（含目标表与启用状态）。"""
    rows: list[dict[str, Any]] = []
    for name in sorted(load_sources()):
        src = load_sources()[name]
        rows.append(
            {
                "source_name": name,
                "source_type": src.get("source_type", ""),
                "system_type": src.get("system_type", ""),
                "target_table": src.get("target_table", ""),
                "load_mode": src.get("load_mode", ""),
                "cron": src.get("cron", ""),
                "enabled": bool(src.get("enabled", True)),
                "location": src.get("location", ""),
                "host": src.get("host", ""),
            }
        )
    return rows


if __name__ == "__main__":  # 手工自检：python -m etl.config.source_config
    print(f"{'数据源':<16}{'类型':<8}{'目标表':<28}{'装载':<6}{'启用'}")
    for row in list_sources():
        print(
            f"{row['source_name']:<16}{row['source_type']:<8}"
            f"{row['target_table']:<28}{row['load_mode']:<6}{'是' if row['enabled'] else '否'}"
        )
    print("\n连接测试：")
    for row in list_sources():
        test_connection(row["source_name"])
