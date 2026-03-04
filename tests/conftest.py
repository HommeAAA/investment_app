from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolated_sqlite_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("ALLOW_SQLITE_FALLBACK", "0")
    monkeypatch.setenv("APP_AUTH_SECRET", "test-secret")

    from app.config import get_settings
    from app import db

    get_settings.cache_clear()
    if db._engine is not None:
        db._engine.dispose()
    db._engine = None
    db.SessionLocal = None

    from app.db import init_db

    init_db()
    yield

    if db._engine is not None:
        db._engine.dispose()
    db._engine = None
    db.SessionLocal = None
