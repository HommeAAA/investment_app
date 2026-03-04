from app.services import AuthService, LogService, MarketService, PortfolioService, ShareService


class FakeMarketService(MarketService):
    def get_symbol_name(self, market: str, code: str) -> str:
        return code

    def get_prices(self, rows):
        return {row.symbol_code: 100.0 for row in rows}


def test_full_flow_register_share_edit_and_logs():
    auth = AuthService()
    auth.ensure_admin_user()
    auth.register("owner", "123")
    auth.register("editor", "123")

    shares = ShareService()
    portfolio = PortfolioService(FakeMarketService())
    logs = LogService()

    created = portfolio.add_investment("owner", "owner", "AAPL", "ib", 90.0, 1)
    assert created.ok is True
    row_id = created.payload.id

    ok, _ = shares.invite("owner", "editor", "edit")
    assert ok is True

    # editor updates owner's record
    updated = portfolio.update_investment("editor", row_id, "owner", 88.0, 2.0)
    assert updated is True

    friendly_logs = logs.list_friendly(limit=50)
    assert any(item["动作"] == "修改" for item in friendly_logs)
    assert any("成本价" in item["变更摘要"] or "数量" in item["变更摘要"] for item in friendly_logs)
