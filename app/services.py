from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import bcrypt
import pandas as pd
import requests
from sqlalchemy import select

from .config import get_settings
from .db import session_scope
from .models import Investment
from .repositories import (
    AuthRepository,
    InvestmentRepository,
    LogRepository,
    PasskeyRepository,
    RepoResult,
    ShareRepository,
    SymbolRepository,
    normalize_permission,
)


@dataclass
class UserSession:
    username: str


@dataclass
class InvestmentView:
    id: int
    investor: str
    market: str
    symbol_code: str
    symbol_name: str
    channel: str
    cost_price: float
    quantity: float
    owner_username: str
    update_time: str
    currency: str
    current_price: float
    total_cost: float
    current_market_value: float
    profit: float
    yield_pct: float


class AuthService:
    def __init__(self) -> None:
        self.settings = get_settings()

    @staticmethod
    def hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        try:
            return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
        except Exception:
            return False

    def sign_payload(self, payload: str) -> str:
        return hmac.new(
            self.settings.auth_secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def make_token(self, username: str) -> str:
        ts = int(time.time())
        payload = f"{username}|{ts}"
        return f"{payload}|{self.sign_payload(payload)}"

    def parse_token(self, token: str | None) -> str | None:
        if not token:
            return None
        try:
            username, ts_str, signature = token.split("|")
            payload = f"{username}|{ts_str}"
            if not hmac.compare_digest(signature, self.sign_payload(payload)):
                return None
            if int(time.time()) - int(ts_str) > self.settings.auth_max_age_seconds:
                return None
            return username
        except Exception:
            return None

    def ensure_admin_user(self) -> None:
        with session_scope() as session:
            AuthRepository.ensure_admin(
                session,
                self.settings.admin_username,
                self.hash_password(self.settings.admin_password),
            )

    def register(self, username: str, password: str) -> tuple[bool, str]:
        with session_scope() as session:
            result = AuthRepository.create_user(session, username, self.hash_password(password))
            return result.ok, "注册成功" if result.ok else result.message

    def login(self, username: str, password: str) -> bool:
        with session_scope() as session:
            user = AuthRepository.get_user(session, username)
            if user is None:
                return False
            return self.verify_password(password, user.password_hash)

    def list_passkeys(self, username: str) -> list[dict[str, Any]]:
        with session_scope() as session:
            rows = PasskeyRepository.list_for_user(session, username)
            return [
                {
                    "id": row.id,
                    "username": row.username,
                    "credential_id": row.credential_id,
                    "public_key": row.public_key,
                    "sign_count": int(row.sign_count or 0),
                    "transports": row.transports or "[]",
                    "created_at": row.created_at,
                    "last_used_at": row.last_used_at,
                }
                for row in rows
            ]

    def get_passkey_by_credential_id(self, credential_id: str) -> dict[str, Any] | None:
        with session_scope() as session:
            row = PasskeyRepository.get_by_credential_id(session, credential_id)
            if row is None:
                return None
            return {
                "id": row.id,
                "username": row.username,
                "credential_id": row.credential_id,
                "public_key": row.public_key,
                "sign_count": int(row.sign_count or 0),
                "transports": row.transports or "[]",
                "created_at": row.created_at,
                "last_used_at": row.last_used_at,
            }

    def upsert_passkey(
        self,
        *,
        username: str,
        credential_id: str,
        public_key: str,
        sign_count: int,
        transports: list[str] | None = None,
    ) -> None:
        payload = json.dumps(transports or [], ensure_ascii=False)
        with session_scope() as session:
            PasskeyRepository.upsert(
                session,
                username=username,
                credential_id=credential_id,
                public_key=public_key,
                sign_count=int(sign_count or 0),
                transports=payload,
            )

    def update_passkey_sign_count(self, credential_id: str, sign_count: int) -> None:
        with session_scope() as session:
            PasskeyRepository.update_sign_count(session, credential_id, int(sign_count or 0))

    def delete_passkey(self, username: str, passkey_id: int) -> bool:
        with session_scope() as session:
            return PasskeyRepository.delete(session, username, int(passkey_id))


class MarketService:
    @staticmethod
    def _yf():
        try:
            import yfinance as yf  # type: ignore

            return yf
        except Exception:
            return None

    @staticmethod
    def identify_market(code: str) -> str:
        code = str(code).upper()
        if "USDT" in code or code in ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE"]:
            return "Crypto"
        if code.isdigit() and len(code) == 6:
            return "A股"
        return "美股"

    @staticmethod
    def market_currency(market: str) -> str:
        if market == "A股":
            return "CNY"
        if market in {"美股", "Crypto"}:
            return "USD"
        return "CNY"

    def get_symbol_name(self, market: str, code: str) -> str:
        code = str(code).strip().upper()
        if market == "A股":
            name = self._a_stock_name(code)
            if name == code:
                name = self._fund_name(code)
            return name
        if market == "美股":
            return self._us_stock_name(code)
        return code

    def _a_stock_name(self, code: str) -> str:
        try:
            secid = ("1." if code.startswith(("6", "5", "9")) else "0.") + code
            r = requests.get(
                "https://push2.eastmoney.com/api/qt/stock/get",
                params={"secid": secid, "fields": "f58"},
                timeout=4,
            )
            return r.json().get("data", {}).get("f58") or code
        except Exception:
            return code

    def _fund_name(self, code: str) -> str:
        try:
            r = requests.get(f"https://fundgz.1234567.com.cn/js/{code}.js", timeout=4)
            text = r.text
            if "jsonpgz" in text:
                start = text.find("{")
                end = text.rfind("}")
                if start != -1 and end != -1:
                    data = json.loads(text[start : end + 1])
                    return data.get("name", code)
        except Exception:
            pass
        return code

    def _us_stock_name(self, code: str) -> str:
        yf = self._yf()
        if yf is None:
            return code
        try:
            return yf.Ticker(code).info.get("shortName", code)
        except Exception:
            return code

    def get_prices(self, rows: list[Investment]) -> dict[str, float]:
        prices: dict[str, float] = {}
        us_codes = sorted({r.symbol_code for r in rows if r.market == "美股"})
        crypto_codes = sorted({r.symbol_code for r in rows if r.market == "Crypto"})

        prices.update(self._us_prices(us_codes))
        prices.update(self._crypto_prices(crypto_codes))

        for row in rows:
            if row.market == "A股":
                prices[row.symbol_code] = self._a_price(row.symbol_code)
        return prices

    def _a_price(self, code: str) -> float:
        try:
            secid = ("1." if code.startswith(("6", "5", "9")) else "0.") + code
            r = requests.get(
                "https://push2.eastmoney.com/api/qt/stock/get",
                params={"secid": secid, "fields": "f43"},
                timeout=4,
            )
            val = r.json().get("data", {}).get("f43")
            if val:
                return float(val) / 100
        except Exception:
            pass

        # fallback to fund NAV
        try:
            r = requests.get(f"https://fundgz.1234567.com.cn/js/{code}.js", timeout=4)
            text = r.text
            if "jsonpgz" in text:
                data = json.loads(text[text.find("{") : text.rfind("}") + 1])
                return float(data.get("gsz", 0))
        except Exception:
            pass
        return 0.0

    def _us_prices(self, codes: list[str]) -> dict[str, float]:
        if not codes:
            return {}
        yf = self._yf()
        if yf is None:
            return {k: 0.0 for k in codes}
        output = {k: 0.0 for k in codes}
        try:
            frame = yf.download(
                tickers=codes,
                period="1d",
                interval="1m",
                auto_adjust=False,
                progress=False,
            )
            if len(codes) == 1:
                code = codes[0]
                output[code] = float(frame["Close"].dropna().iloc[-1].item())
            else:
                for code in codes:
                    try:
                        output[code] = float(frame["Close"][code].dropna().iloc[-1].item())
                    except Exception:
                        pass
        except Exception:
            pass

        for code in codes:
            if output[code] > 0:
                continue
            try:
                info = yf.Ticker(code).fast_info
                output[code] = float(info.get("lastPrice") or info.get("regularMarketPrice") or 0)
            except Exception:
                output[code] = 0.0
        return output

    def _crypto_prices(self, codes: list[str]) -> dict[str, float]:
        if not codes:
            return {}
        out = {k: 0.0 for k in codes}
        try:
            data = requests.get("https://api.binance.com/api/v3/ticker/price", timeout=6).json()
            mapping = {x["symbol"]: float(x["price"]) for x in data}
            for code in codes:
                key = code if code.endswith("USDT") else f"{code}USDT"
                out[code] = float(mapping.get(key, 0.0))
        except Exception:
            pass
        return out

    def fx_rates(self) -> dict[str, float]:
        rates = {"USD": 1.0, "CNY": 7.2}
        try:
            r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=6)
            data = r.json()
            if data.get("result") == "success":
                rates["CNY"] = float(data.get("rates", {}).get("CNY", 7.2))
        except Exception:
            pass
        return rates

    @staticmethod
    def convert_amount(amount: float, from_currency: str, to_currency: str, rates: dict[str, float]) -> float:
        amount = float(amount or 0)
        from_ccy = from_currency.upper()
        to_ccy = to_currency.upper()
        if from_ccy == to_ccy:
            return amount
        if from_ccy not in rates or to_ccy not in rates:
            return amount
        usd_amount = amount / float(rates[from_ccy])
        return usd_amount * float(rates[to_ccy])


class PortfolioService:
    def __init__(self, market_service: MarketService) -> None:
        self.market = market_service

    def list_investor_options(self, username: str, owner_only: bool = True) -> list[str]:
        with session_scope() as session:
            names = InvestmentRepository.investor_names(session, username, owner_only=owner_only)
        options = [username] if username else []
        for name in names:
            if name and name not in options:
                options.append(name)
        options.append("新增投资人")
        return options

    def seed_symbol_cache_from_investments(self) -> None:
        with session_scope() as session:
            rows = session.scalars(select(Investment)).all()
            payload = [(r.market, r.symbol_code, r.symbol_name) for r in rows if r.symbol_code and r.symbol_name]
            SymbolRepository.upsert_many(session, payload, source="investments")

    def search_symbol_options(self, keyword: str, limit: int = 20) -> list[dict[str, str]]:
        keyword = str(keyword or "").strip()
        if not keyword:
            return []
        with session_scope() as session:
            rows = SymbolRepository.search(session, keyword, limit=limit)
        return [
            {"market": row.market, "symbol_code": row.symbol_code, "symbol_name": row.symbol_name}
            for row in rows
        ]

    def upsert_symbol_cache(self, market: str, code: str, name: str, source: str = "manual") -> None:
        with session_scope() as session:
            SymbolRepository.upsert_many(session, [(market, code, name)], source=source)

    def delete_investor_and_reassign(self, username: str, from_name: str, to_name: str) -> int:
        from_name = str(from_name).strip()
        to_name = str(to_name).strip() or username
        if not from_name:
            return 0

        with session_scope() as session:
            affected = InvestmentRepository.reassign_investor(session, username, from_name, to_name)
            if affected > 0:
                LogRepository.write(
                    session,
                    entity_type="investor_profile",
                    entity_id=0,
                    action="delete",
                    operator=username,
                    owner=username,
                    before_data={"investor": from_name},
                    after_data={"investor": to_name, "affected_records": affected},
                )
            return affected

    def add_investment(
        self,
        username: str,
        investor: str,
        symbol_code: str,
        channel: str,
        cost_price: float,
        quantity: float,
    ) -> RepoResult:
        symbol_code = str(symbol_code).strip().upper()
        investor = str(investor).strip() or username
        if not symbol_code or quantity <= 0:
            return RepoResult(ok=False, message="请输入有效标的代码和数量")

        market = self.market.identify_market(symbol_code)

        with session_scope() as session:
            cached_name = SymbolRepository.get_cached_name(session, market, symbol_code)
            symbol_name = cached_name or self.market.get_symbol_name(market, symbol_code)
            row = InvestmentRepository.create(
                session,
                investor=investor,
                market=market,
                symbol_code=symbol_code,
                symbol_name=symbol_name,
                channel=channel,
                cost_price=cost_price,
                quantity=quantity,
                owner_username=username,
            )
            SymbolRepository.upsert_many(session, [(market, symbol_code, symbol_name)], source="user_submit")
            LogRepository.write(
                session,
                entity_type="investment",
                entity_id=row.id,
                action="create",
                operator=username,
                owner=username,
                after_data={
                    "investor": investor,
                    "market": market,
                    "symbol_code": symbol_code,
                    "symbol_name": symbol_name,
                    "channel": channel,
                    "cost_price": float(cost_price),
                    "quantity": float(quantity),
                    "user": username,
                },
            )
            return RepoResult(ok=True, payload=row)

    def update_investment(
        self,
        username: str,
        investment_id: int,
        investor: str,
        cost_price: float,
        quantity: float,
    ) -> bool:
        investor = str(investor).strip() or username
        with session_scope() as session:
            row = InvestmentRepository.get_by_id(session, investment_id)
            if row is None:
                return False
            if not ShareRepository.can_edit_owner_data(session, row.owner_username, username):
                return False

            before = {
                "investor": row.investor,
                "market": row.market,
                "symbol_code": row.symbol_code,
                "symbol_name": row.symbol_name,
                "channel": row.channel,
                "cost_price": float(row.cost_price),
                "quantity": float(row.quantity),
                "user": row.owner_username,
            }
            InvestmentRepository.update(
                session,
                row=row,
                investor=investor,
                cost_price=cost_price,
                quantity=quantity,
            )
            after = {**before, "investor": investor, "cost_price": float(cost_price), "quantity": float(quantity)}
            LogRepository.write(
                session,
                entity_type="investment",
                entity_id=row.id,
                action="update",
                operator=username,
                owner=row.owner_username,
                before_data=before,
                after_data=after,
            )
            return True

    def delete_investment(self, username: str, investment_id: int) -> bool:
        with session_scope() as session:
            row = InvestmentRepository.get_by_id(session, investment_id)
            if row is None:
                return False
            if not ShareRepository.can_edit_owner_data(session, row.owner_username, username):
                return False

            before = {
                "investor": row.investor,
                "market": row.market,
                "symbol_code": row.symbol_code,
                "symbol_name": row.symbol_name,
                "channel": row.channel,
                "cost_price": float(row.cost_price),
                "quantity": float(row.quantity),
                "user": row.owner_username,
            }
            InvestmentRepository.delete(session, row)
            LogRepository.write(
                session,
                entity_type="investment",
                entity_id=investment_id,
                action="delete",
                operator=username,
                owner=before["user"],
                before_data=before,
            )
            return True

    def accessible_view_rows(self, username: str) -> list[InvestmentView]:
        with session_scope() as session:
            rows = InvestmentRepository.list_accessible(session, username)

        prices = self.market.get_prices(rows)
        output: list[InvestmentView] = []
        for row in rows:
            current_price = float(prices.get(row.symbol_code, 0.0))
            total_cost = float(row.cost_price) * float(row.quantity)
            current_mv = current_price * float(row.quantity)
            profit = current_mv - total_cost
            yield_pct = round((profit / total_cost) * 100, 2) if total_cost > 0 else 0
            output.append(
                InvestmentView(
                    id=row.id,
                    investor=row.investor,
                    market=row.market,
                    symbol_code=row.symbol_code,
                    symbol_name=row.symbol_name,
                    channel=row.channel,
                    cost_price=float(row.cost_price),
                    quantity=float(row.quantity),
                    owner_username=row.owner_username,
                    update_time=row.update_time.strftime("%Y-%m-%d %H:%M:%S"),
                    currency=self.market.market_currency(row.market),
                    current_price=current_price,
                    total_cost=total_cost,
                    current_market_value=current_mv,
                    profit=profit,
                    yield_pct=yield_pct,
                )
            )
        return output

    def valuation_summary(self, rows: list[InvestmentView], valuation_mode: str) -> dict[str, Any]:
        if not rows:
            return {"mode": valuation_mode, "groups": []}

        if valuation_mode == "人民币 (CNY)":
            target = "CNY"
        elif valuation_mode == "美元 (USD)":
            target = "USD"
        else:
            target = None

        if target:
            rates = self.market.fx_rates()
            total_cost = sum(
                self.market.convert_amount(r.total_cost, r.currency, target, rates) for r in rows
            )
            total_mv = sum(
                self.market.convert_amount(r.current_market_value, r.currency, target, rates)
                for r in rows
            )
            total_profit = total_mv - total_cost
            total_yield = round((total_profit / total_cost) * 100, 2) if total_cost > 0 else 0
            return {
                "mode": valuation_mode,
                "groups": [
                    {
                        "currency": target,
                        "total_cost": total_cost,
                        "total_mv": total_mv,
                        "total_profit": total_profit,
                        "total_yield": total_yield,
                    }
                ],
            }

        grouped: dict[str, dict[str, float]] = {}
        for row in rows:
            grouped.setdefault(
                row.currency,
                {"total_cost": 0.0, "total_mv": 0.0},
            )
            grouped[row.currency]["total_cost"] += row.total_cost
            grouped[row.currency]["total_mv"] += row.current_market_value

        groups = []
        for currency, values in grouped.items():
            total_cost = values["total_cost"]
            total_mv = values["total_mv"]
            total_profit = total_mv - total_cost
            total_yield = round((total_profit / total_cost) * 100, 2) if total_cost > 0 else 0
            groups.append(
                {
                    "currency": currency,
                    "total_cost": total_cost,
                    "total_mv": total_mv,
                    "total_profit": total_profit,
                    "total_yield": total_yield,
                }
            )
        return {"mode": valuation_mode, "groups": groups}


class ShareService:
    def invite(self, owner: str, shared_with: str, permission: str) -> tuple[bool, str]:
        if owner == shared_with:
            return False, "不能邀请自己"
        permission = normalize_permission(permission)

        with session_scope() as session:
            user = AuthRepository.get_user(session, shared_with)
            if user is None:
                return False, "用户不存在"
            result = ShareRepository.invite(session, owner, shared_with, permission)
            return result.ok, "✅ 已邀请" if result.ok else result.message

    def revoke(self, owner: str, shared_with: str) -> None:
        with session_scope() as session:
            ShareRepository.revoke(session, owner, shared_with)

    def invited(self, owner: str) -> list[dict[str, str]]:
        with session_scope() as session:
            rows = ShareRepository.list_invited(session, owner)
            return [
                {"shared_with": row.shared_with, "permission": normalize_permission(row.permission)}
                for row in rows
            ]

    def permission_map(self, username: str) -> dict[str, str]:
        with session_scope() as session:
            return ShareRepository.permission_map_for_user(session, username)

    def can_edit(self, owner: str, actor: str) -> bool:
        with session_scope() as session:
            return ShareRepository.can_edit_owner_data(session, owner, actor)


class LogService:
    def list_friendly(self, limit: int = 200) -> list[dict[str, Any]]:
        with session_scope() as session:
            rows = LogRepository.list_recent(session, limit=limit)

        field_alias = {
            "investor": "投资人",
            "market": "市场",
            "symbol_code": "代码",
            "symbol_name": "名称",
            "channel": "渠道",
            "cost_price": "成本价",
            "quantity": "数量",
            "user": "归属人",
        }
        action_alias = {"create": "新增", "update": "修改", "delete": "删除"}
        entity_alias = {"investment": "投资记录", "investor_profile": "投资人"}

        out: list[dict[str, Any]] = []
        for row in rows:
            before = json.loads(row.before_data) if row.before_data else {}
            after = json.loads(row.after_data) if row.after_data else {}

            if row.action == "update":
                parts = []
                keys = sorted(set(before.keys()) | set(after.keys()))
                for key in keys:
                    if before.get(key) == after.get(key):
                        continue
                    parts.append(f"{field_alias.get(key, key)}: {before.get(key)} -> {after.get(key)}")
                summary = "；".join(parts) if parts else "无关键字段变化"
            elif row.action == "create":
                summary = "新增记录"
            else:
                summary = "删除记录"

            source = after if after else before
            target = f"{source.get('investor', '')} / {source.get('symbol_name', '')}({source.get('symbol_code', '')})".strip(" /")
            if not target:
                target = f"{row.entity_type}#{row.entity_id}"

            out.append(
                {
                    "时间": row.action_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "操作人": row.operator,
                    "动作": action_alias.get(row.action, row.action),
                    "对象": entity_alias.get(row.entity_type, row.entity_type),
                    "标的": target,
                    "归属人": row.owner,
                    "变更摘要": summary,
                }
            )
        return out
