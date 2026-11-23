"""应用配置（阶段四 · 步骤 1）。

集中管理数据库连接、JWT 密钥与有效期、LLM 接口地址、分页与导出限制等配置；
全部支持环境变量覆盖，禁止在代码中硬编码密钥。`get_settings()` 使用 lru_cache 单例。

环境变量前缀：MOA_（例如 MOA_JWT_SECRET、MOA_DB_URL、MOA_LLM_BASE_URL）。
同时兼容工程既有的 DB_URL / DB_HOST / DB_USER / DB_PASSWORD / DB_NAME 约定。
"""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置对象。"""

    model_config = SettingsConfigDict(env_prefix="MOA_", env_file=".env", extra="ignore")

    # ---------------- 应用 ----------------
    app_name: str = "医疗运营数据主题分析平台 API"
    app_version: str = "0.1.0"
    app_env: str = Field(default="dev", description="运行环境：dev / test / prod")
    api_prefix: str = "/api"
    debug: bool = False
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1",
        ]
    )

    # ---------------- 数据库 ----------------
    db_url: str | None = Field(default=None, description="完整 SQLAlchemy URL，优先级最高")
    db_echo: bool = False

    # ---------------- 认证鉴权 ----------------
    jwt_secret: str = Field(default="please-change-this-secret-in-production")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = Field(default=480, description="访问令牌有效期（分钟），支持环境变量覆盖")
    jwt_issuer: str = "medical-ops-analytics"
    default_admin_password: str = "Admin@123"

    # ---------------- 大模型（阶段六使用） ----------------
    llm_provider: str = "openai"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: int = 180

    # ---------------- 查询与导出 ----------------
    query_max_rows: int = Field(default=5000, description="单次查询最大返回行数")
    export_max_rows: int = Field(default=20000, description="导出最大行数")
    export_dir: str = "uploads"
    default_granularity: str = "month"

    # ---------------- ETL 日志与报告 ----------------
    etl_log_dir: str = Field(default="", description="留空则使用 backend/etl/logs")

    def resolved_db_url(self) -> str:
        """解析数据库连接串：MOA_DB_URL > DB_URL > DB_HOST 分项 > 本地 SQLite。"""
        if self.db_url:
            return self.db_url
        for env_key in ("DB_URL", "MOA_DB_URL"):
            value = os.getenv(env_key)
            if value:
                return value
        host = os.getenv("DB_HOST")
        if host:
            user = os.getenv("DB_USER", "moa")
            password = os.getenv("DB_PASSWORD", "")
            port = os.getenv("DB_PORT", "3306")
            name = os.getenv("DB_NAME", "medical_ops")
            return f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}?charset=utf8mb4"
        from pathlib import Path

        log_dir = Path(__file__).resolve().parents[2] / "etl" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{(log_dir / 'moa_dev.db').as_posix()}"

    @property
    def is_prod(self) -> bool:
        return self.app_env.lower() in {"prod", "production"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """获取配置单例（lru_cache 保证进程内只解析一次）。"""
    return Settings()


def reset_settings_cache() -> None:
    """清空配置缓存（测试或热更新环境变量后调用）。"""
    get_settings.cache_clear()
