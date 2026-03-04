from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    app_name: str
    database_url: str
    sqlite_fallback_url: str
    allow_sqlite_fallback: bool
    auth_secret: str
    auth_max_age_seconds: int
    admin_username: str
    admin_password: str


def _read_setting(name: str, default: str = "") -> str:
    env_value = os.getenv(name, "").strip()
    if env_value:
        return env_value
    try:
        import streamlit as st  # local import to avoid hard dependency at module import time

        secret_value = st.secrets.get(name, "")
        if isinstance(secret_value, str):
            secret_value = secret_value.strip()
        return secret_value or default
    except Exception:
        return default


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        app_name="全球资产管理系统 Pro",
        database_url=_read_setting(
            "DATABASE_URL",
            "postgresql+psycopg://postgres:postgres@localhost:5432/investment_app",
        ),
        sqlite_fallback_url=_read_setting(
            "SQLITE_FALLBACK_URL", "sqlite:////tmp/investment_app_dev.db"
        ),
        allow_sqlite_fallback=_read_setting("ALLOW_SQLITE_FALLBACK", "0") == "1",
        auth_secret=_read_setting("APP_AUTH_SECRET", "change-me-in-production"),
        auth_max_age_seconds=int(_read_setting("APP_AUTH_MAX_AGE", str(7 * 24 * 60 * 60))),
        admin_username=_read_setting("APP_ADMIN_USERNAME", "admin"),
        admin_password=_read_setting("APP_ADMIN_PASSWORD", "admin123"),
    )
