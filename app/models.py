from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class Investment(Base):
    __tablename__ = "investments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    investor: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    market: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    symbol_code: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    symbol_name: Mapped[str] = mapped_column(String(255), nullable=False)
    channel: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    cost_price: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    owner_username: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class Share(Base):
    __tablename__ = "shares"
    __table_args__ = (UniqueConstraint("owner", "shared_with", name="uq_share_owner_shared"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    shared_with: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    permission: Mapped[str] = mapped_column(String(10), default="read", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class OperationLog(Base):
    __tablename__ = "operation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    operator: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    owner: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    changed_fields: Mapped[str | None] = mapped_column(Text, nullable=True)
    before_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_time: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)


class SymbolCache(Base):
    __tablename__ = "symbol_cache"
    __table_args__ = (UniqueConstraint("market", "symbol_code", name="uq_symbol_market_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    symbol_code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    symbol_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(50), default="manual", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class AppMeta(Base):
    __tablename__ = "app_meta"

    meta_key: Mapped[str] = mapped_column(String(120), primary_key=True)
    meta_value: Mapped[str] = mapped_column(Text, default="", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class UserPasskey(Base):
    __tablename__ = "user_passkeys"
    __table_args__ = (UniqueConstraint("credential_id", name="uq_user_passkeys_credential"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    credential_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    public_key: Mapped[str] = mapped_column(Text, nullable=False)
    sign_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    transports: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_used_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
