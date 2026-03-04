from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import AppMeta, Investment, OperationLog, Share, SymbolCache, User, UserPasskey


@dataclass
class RepoResult:
    ok: bool
    message: str = ""
    payload: Any = None


def normalize_permission(permission: str) -> str:
    return "edit" if permission == "edit" else "read"


class AuthRepository:
    @staticmethod
    def get_user(session: Session, username: str) -> User | None:
        return session.scalar(select(User).where(User.username == username))

    @staticmethod
    def create_user(session: Session, username: str, password_hash: str) -> RepoResult:
        user = User(username=username, password_hash=password_hash)
        session.add(user)
        try:
            session.flush()
            return RepoResult(ok=True, payload=user)
        except IntegrityError:
            session.rollback()
            return RepoResult(ok=False, message="用户名已存在")

    @staticmethod
    def ensure_admin(session: Session, username: str, password_hash: str) -> None:
        exists = session.scalar(select(func.count()).select_from(User).where(User.username == username))
        if not exists:
            session.add(User(username=username, password_hash=password_hash))
            session.flush()


class PasskeyRepository:
    @staticmethod
    def list_for_user(session: Session, username: str) -> list[UserPasskey]:
        return list(
            session.scalars(
                select(UserPasskey).where(UserPasskey.username == username).order_by(desc(UserPasskey.id))
            )
        )

    @staticmethod
    def get_by_credential_id(session: Session, credential_id: str) -> UserPasskey | None:
        return session.scalar(select(UserPasskey).where(UserPasskey.credential_id == credential_id))

    @staticmethod
    def upsert(
        session: Session,
        *,
        username: str,
        credential_id: str,
        public_key: str,
        sign_count: int,
        transports: str,
    ) -> UserPasskey:
        row = session.scalar(select(UserPasskey).where(UserPasskey.credential_id == credential_id))
        now = datetime.utcnow()
        if row is None:
            row = UserPasskey(
                username=username,
                credential_id=credential_id,
                public_key=public_key,
                sign_count=int(sign_count or 0),
                transports=transports,
                created_at=now,
                last_used_at=now,
            )
            session.add(row)
            session.flush()
            return row

        row.username = username
        row.public_key = public_key
        row.sign_count = int(sign_count or 0)
        row.transports = transports
        row.last_used_at = now
        session.flush()
        return row

    @staticmethod
    def update_sign_count(session: Session, credential_id: str, sign_count: int) -> None:
        row = session.scalar(select(UserPasskey).where(UserPasskey.credential_id == credential_id))
        if row is None:
            return
        row.sign_count = int(sign_count or 0)
        row.last_used_at = datetime.utcnow()
        session.flush()

    @staticmethod
    def delete(session: Session, username: str, passkey_id: int) -> bool:
        row = session.scalar(
            select(UserPasskey).where(and_(UserPasskey.id == int(passkey_id), UserPasskey.username == username))
        )
        if row is None:
            return False
        session.delete(row)
        session.flush()
        return True


class ShareRepository:
    @staticmethod
    def invite(session: Session, owner: str, shared_with: str, permission: str) -> RepoResult:
        permission = normalize_permission(permission)
        row = session.scalar(
            select(Share).where(and_(Share.owner == owner, Share.shared_with == shared_with))
        )
        if row is None:
            row = Share(owner=owner, shared_with=shared_with, permission=permission)
            session.add(row)
            session.flush()
            return RepoResult(ok=True, message="邀请成功", payload=row)

        row.permission = permission
        row.created_at = datetime.utcnow()
        session.flush()
        return RepoResult(ok=True, message="权限已更新", payload=row)

    @staticmethod
    def revoke(session: Session, owner: str, shared_with: str) -> None:
        row = session.scalar(
            select(Share).where(and_(Share.owner == owner, Share.shared_with == shared_with))
        )
        if row:
            session.delete(row)
            session.flush()

    @staticmethod
    def list_invited(session: Session, owner: str) -> list[Share]:
        return list(session.scalars(select(Share).where(Share.owner == owner).order_by(Share.shared_with)))

    @staticmethod
    def permission_map_for_user(session: Session, shared_with: str) -> dict[str, str]:
        rows = session.scalars(select(Share).where(Share.shared_with == shared_with)).all()
        return {r.owner: normalize_permission(r.permission) for r in rows}

    @staticmethod
    def can_edit_owner_data(session: Session, owner: str, actor: str) -> bool:
        if owner == actor:
            return True
        row = session.scalar(
            select(Share).where(and_(Share.owner == owner, Share.shared_with == actor))
        )
        return bool(row and normalize_permission(row.permission) == "edit")


class InvestmentRepository:
    @staticmethod
    def accessible_owners(session: Session, username: str) -> list[str]:
        mapping = ShareRepository.permission_map_for_user(session, username)
        owners = {username, *mapping.keys()}
        return sorted(list(owners))

    @staticmethod
    def list_accessible(session: Session, username: str) -> list[Investment]:
        owners = InvestmentRepository.accessible_owners(session, username)
        stmt = select(Investment).where(Investment.owner_username.in_(owners)).order_by(desc(Investment.update_time))
        return list(session.scalars(stmt))

    @staticmethod
    def list_owner_only(session: Session, username: str) -> list[Investment]:
        stmt = select(Investment).where(Investment.owner_username == username)
        return list(session.scalars(stmt))

    @staticmethod
    def get_by_id(session: Session, investment_id: int) -> Investment | None:
        return session.scalar(select(Investment).where(Investment.id == investment_id))

    @staticmethod
    def create(
        session: Session,
        *,
        investor: str,
        market: str,
        symbol_code: str,
        symbol_name: str,
        channel: str,
        cost_price: float,
        quantity: float,
        owner_username: str,
    ) -> Investment:
        row = Investment(
            investor=investor,
            market=market,
            symbol_code=symbol_code,
            symbol_name=symbol_name,
            channel=channel,
            cost_price=float(cost_price),
            quantity=float(quantity),
            owner_username=owner_username,
            update_time=datetime.utcnow(),
        )
        session.add(row)
        session.flush()
        return row

    @staticmethod
    def update(
        session: Session,
        *,
        row: Investment,
        investor: str,
        cost_price: float,
        quantity: float,
    ) -> Investment:
        row.investor = investor
        row.cost_price = float(cost_price)
        row.quantity = float(quantity)
        row.update_time = datetime.utcnow()
        session.flush()
        return row

    @staticmethod
    def delete(session: Session, row: Investment) -> None:
        session.delete(row)
        session.flush()

    @staticmethod
    def investor_names(session: Session, username: str, owner_only: bool = True) -> list[str]:
        if owner_only:
            stmt = select(Investment.investor).where(Investment.owner_username == username)
        else:
            owners = InvestmentRepository.accessible_owners(session, username)
            stmt = select(Investment.investor).where(Investment.owner_username.in_(owners))
        rows = [str(x).strip() for x in session.scalars(stmt) if str(x).strip()]
        return sorted(list(set(rows)))

    @staticmethod
    def reassign_investor(session: Session, owner: str, from_investor: str, to_investor: str) -> int:
        rows = session.scalars(
            select(Investment).where(
                and_(
                    Investment.owner_username == owner,
                    Investment.investor == from_investor,
                )
            )
        ).all()
        for row in rows:
            row.investor = to_investor
            row.update_time = datetime.utcnow()
        session.flush()
        return len(rows)


class LogRepository:
    @staticmethod
    def write(
        session: Session,
        *,
        entity_type: str,
        entity_id: int,
        action: str,
        operator: str,
        owner: str,
        before_data: dict[str, Any] | None = None,
        after_data: dict[str, Any] | None = None,
    ) -> None:
        changed_fields = None
        if isinstance(before_data, dict) and isinstance(after_data, dict):
            keys = sorted(set(before_data.keys()) | set(after_data.keys()))
            changed = [k for k in keys if before_data.get(k) != after_data.get(k)]
            changed_fields = ",".join(changed)

        row = OperationLog(
            entity_type=entity_type,
            entity_id=int(entity_id),
            action=action,
            operator=operator,
            owner=owner,
            changed_fields=changed_fields,
            before_data=json.dumps(before_data, ensure_ascii=False, sort_keys=True) if before_data else None,
            after_data=json.dumps(after_data, ensure_ascii=False, sort_keys=True) if after_data else None,
            action_time=datetime.utcnow(),
        )
        session.add(row)
        session.flush()

    @staticmethod
    def list_recent(session: Session, limit: int = 200) -> list[OperationLog]:
        stmt = select(OperationLog).order_by(desc(OperationLog.id)).limit(limit)
        return list(session.scalars(stmt))


class SymbolRepository:
    @staticmethod
    def upsert_many(session: Session, rows: list[tuple[str, str, str]], source: str = "manual") -> int:
        if not rows:
            return 0

        count = 0
        now = datetime.utcnow()
        for market, code, name in rows:
            market = str(market).strip()
            code = str(code).strip().upper()
            name = str(name).strip()
            if not market or not code or not name:
                continue

            item = session.scalar(
                select(SymbolCache).where(and_(SymbolCache.market == market, SymbolCache.symbol_code == code))
            )
            if item is None:
                item = SymbolCache(
                    market=market,
                    symbol_code=code,
                    symbol_name=name,
                    source=source,
                    updated_at=now,
                )
                session.add(item)
            else:
                item.symbol_name = name
                item.source = source
                item.updated_at = now
            count += 1

        session.flush()
        return count

    @staticmethod
    def get_cached_name(session: Session, market: str, code: str) -> str:
        code = str(code).strip().upper()
        market = str(market).strip()
        row = session.scalar(
            select(SymbolCache.symbol_name).where(
                and_(SymbolCache.market == market, SymbolCache.symbol_code == code)
            )
        )
        if row:
            return row
        row = session.scalar(
            select(SymbolCache.symbol_name).where(SymbolCache.symbol_code == code).order_by(desc(SymbolCache.updated_at))
        )
        return row or ""

    @staticmethod
    def search(session: Session, keyword: str, limit: int = 20) -> list[SymbolCache]:
        kw = str(keyword).strip()
        if not kw:
            return []
        
        kw_upper = kw.upper()
        like_code = f"%{kw_upper}%"
        like_name = f"%{kw}%"
        
        results = []
        seen = set()
        
        cache_stmt = (
            select(SymbolCache)
            .where(
                or_(
                    func.upper(SymbolCache.symbol_code).like(like_code),
                    SymbolCache.symbol_name.like(like_name),
                )
            )
            .order_by(desc(SymbolCache.updated_at))
        )
        for item in session.scalars(cache_stmt):
            key = (item.market, item.symbol_code)
            if key not in seen:
                seen.add(key)
                results.append(item)
                if len(results) >= limit:
                    break
        
        if len(results) < limit:
            investment_stmt = (
                select(Investment)
                .where(
                    or_(
                        func.upper(Investment.symbol_code).like(like_code),
                        Investment.symbol_name.like(like_name),
                    )
                )
                .order_by(desc(Investment.update_time))
            )
            for item in session.scalars(investment_stmt):
                key = (item.market, item.symbol_code)
                if key not in seen:
                    seen.add(key)
                    cache_item = SymbolCache(
                        market=item.market,
                        symbol_code=item.symbol_code,
                        symbol_name=item.symbol_name,
                        source="investment_search",
                        updated_at=datetime.utcnow(),
                    )
                    results.append(cache_item)
                    if len(results) >= limit:
                        break
        
        return results[:limit]


class MetaRepository:
    @staticmethod
    def get(session: Session, key: str, default: str = "") -> str:
        row = session.scalar(select(AppMeta).where(AppMeta.meta_key == key))
        return row.meta_value if row else default

    @staticmethod
    def set(session: Session, key: str, value: str) -> None:
        row = session.scalar(select(AppMeta).where(AppMeta.meta_key == key))
        if row is None:
            row = AppMeta(meta_key=key, meta_value=value, updated_at=datetime.utcnow())
            session.add(row)
        else:
            row.meta_value = value
            row.updated_at = datetime.utcnow()
        session.flush()
