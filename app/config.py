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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        app_name="全球资产管理系统 Pro",
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://postgres:postgres@localhost:5432/investment_app",
        ),
        sqlite_fallback_url=os.getenv(
            "SQLITE_FALLBACK_URL", "sqlite:////tmp/investment_app_dev.db"
        ),
        allow_sqlite_fallback=os.getenv("ALLOW_SQLITE_FALLBACK", "1") == "1",
        auth_secret=os.getenv("APP_AUTH_SECRET", "change-me-in-production"),
        auth_max_age_seconds=int(os.getenv("APP_AUTH_MAX_AGE", str(7 * 24 * 60 * 60))),
        admin_username=os.getenv("APP_ADMIN_USERNAME", "admin"),
        admin_password=os.getenv("APP_ADMIN_PASSWORD", "admin123"),
    )
