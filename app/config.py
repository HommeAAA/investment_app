from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from collections.abc import Mapping
from typing import Any


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


def _normalize_database_url(url: str) -> str:
    value = str(url or "").strip()
    if value.startswith("postgres://"):
        return "postgresql+psycopg://" + value[len("postgres://") :]
    if value.startswith("postgresql://"):
        return "postgresql+psycopg://" + value[len("postgresql://") :]
    return value


def _read_secret_path(data: Any, path: list[str]) -> str:
    node = data
    for key in path:
        if isinstance(node, Mapping) and key in node:
            node = node[key]
        else:
            return ""
    if isinstance(node, str):
        return node.strip()
    return ""


def _read_database_url(default: str) -> str:
    env_candidates = [
        "DATABASE_URL",
        "database_url",
        "POSTGRES_URL",
        "POSTGRESQL_URL",
        "DB_URL",
    ]
    for name in env_candidates:
        value = os.getenv(name, "").strip()
        if value:
            return _normalize_database_url(value)

    try:
        import streamlit as st  # local import to avoid hard dependency at module import time

        secrets = st.secrets
        direct_keys = ["DATABASE_URL", "database_url", "POSTGRES_URL", "POSTGRESQL_URL", "DB_URL"]
        for key in direct_keys:
            value = secrets.get(key, "")
            if isinstance(value, str) and value.strip():
                return _normalize_database_url(value)

        nested_paths = [
            ["database", "url"],
            ["db", "url"],
            ["postgres", "url"],
            ["postgresql", "url"],
            ["connections", "postgresql", "url"],
            ["connections", "postgres", "url"],
            ["connections", "db", "url"],
        ]
        for path in nested_paths:
            value = _read_secret_path(secrets, path)
            if value:
                return _normalize_database_url(value)
    except Exception:
        pass

    return _normalize_database_url(default)


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
    import platform
    system = platform.system()
    if system == "Windows":
        default_sqlite_path = "sqlite:///investment_app_dev.db"
    else:
        default_sqlite_path = "sqlite:////tmp/investment_app_dev.db"
    
    return Settings(
        app_name="全球资产管理系统 Pro",
        database_url=_read_database_url(
            "postgresql+psycopg://postgres:postgres@localhost:5432/investment_app",
        ),
        sqlite_fallback_url=_read_setting(
            "SQLITE_FALLBACK_URL", default_sqlite_path
        ),
        allow_sqlite_fallback=_read_setting("ALLOW_SQLITE_FALLBACK", "1") == "1",
        auth_secret=_read_setting("APP_AUTH_SECRET", "change-me-in-production"),
        auth_max_age_seconds=int(_read_setting("APP_AUTH_MAX_AGE", str(7 * 24 * 60 * 60))),
        admin_username=_read_setting("APP_ADMIN_USERNAME", "admin"),
        admin_password=_read_setting("APP_ADMIN_PASSWORD", "admin123"),
    )
