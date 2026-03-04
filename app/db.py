from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.exc import NoSuchModuleError, OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, scoped_session, sessionmaker

from .config import get_settings


logger = logging.getLogger("investment_app.db")


class Base(DeclarativeBase):
    pass


_engine = None
SessionLocal = None


def _connectable_engine(url: str):
    return create_engine(url, pool_pre_ping=True, future=True)


def get_engine():
    global _engine, SessionLocal
    if _engine is not None:
        return _engine

    settings = get_settings()
    try:
        _engine = _connectable_engine(settings.database_url)
        with _engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Using database: %s", settings.database_url)
    except (NoSuchModuleError, OperationalError, ModuleNotFoundError) as exc:
        if not settings.allow_sqlite_fallback:
            raise
        logger.warning(
            "Primary database unavailable (%s). Falling back to SQLite: %s",
            exc,
            settings.sqlite_fallback_url,
        )
        _engine = _connectable_engine(settings.sqlite_fallback_url)

    SessionLocal = scoped_session(
        sessionmaker(bind=_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    )
    return _engine


def get_session() -> Session:
    get_engine()
    assert SessionLocal is not None
    return SessionLocal()


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    from . import models  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
