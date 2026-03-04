from app.services import AuthService, MarketService, PortfolioService


class FakeMarketService(MarketService):
    def get_symbol_name(self, market: str, code: str) -> str:
        return f"{code}_NAME"

    def get_prices(self, rows):
        mapping = {
            "600519": 1000.0,
            "AAPL": 200.0,
            "BTC": 30000.0,
        }
        return {row.symbol_code: mapping.get(row.symbol_code, 0.0) for row in rows}

    def fx_rates(self):
        return {"USD": 1.0, "CNY": 7.2}


def test_add_update_delete_and_valuation_modes():
    auth = AuthService()
    auth.ensure_admin_user()
    auth.register("owner", "123")

    market = FakeMarketService()
    svc = PortfolioService(market)

    r1 = svc.add_investment("owner", "owner", "600519", "券商", 900.0, 2)
    r2 = svc.add_investment("owner", "owner", "AAPL", "Robinhood", 150.0, 3)
    assert r1.ok and r2.ok

    rows = svc.accessible_view_rows("owner")
    assert len(rows) == 2

    cny = svc.valuation_summary(rows, "人民币 (CNY)")
    usd = svc.valuation_summary(rows, "美元 (USD)")
    native = svc.valuation_summary(rows, "原币种")

    assert len(cny["groups"]) == 1
    assert len(usd["groups"]) == 1
    assert len(native["groups"]) >= 2

    target = rows[0]
    updated = svc.update_investment("owner", target.id, "new_investor", target.cost_price, target.quantity + 1)
    assert updated is True

    rows2 = svc.accessible_view_rows("owner")
    assert any(r.investor == "new_investor" for r in rows2)

    deleted = svc.delete_investment("owner", rows2[0].id)
    assert deleted is True
    assert len(svc.accessible_view_rows("owner")) == 1


def test_delete_investor_and_reassign():
    auth = AuthService()
    auth.ensure_admin_user()
    auth.register("u1", "123")

    svc = PortfolioService(FakeMarketService())
    svc.add_investment("u1", "old_name", "600519", "a", 10.0, 1)
    svc.add_investment("u1", "old_name", "AAPL", "b", 10.0, 1)

    affected = svc.delete_investor_and_reassign("u1", "old_name", "u1")
    assert affected == 2

    rows = svc.accessible_view_rows("u1")
    assert all(r.investor == "u1" for r in rows)
