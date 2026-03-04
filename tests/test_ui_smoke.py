from app import ui


def test_tab_keys_unique():
    keys = [k for k, _ in ui.TAB_ITEMS]
    assert len(keys) == len(set(keys))


def test_default_tab_portfolio(monkeypatch):
    monkeypatch.setattr(ui, "get_query_value", lambda key: None)
    ui.st.session_state.current_tab = "portfolio"
    assert ui.get_current_tab() == "portfolio"


def test_query_tab_has_priority(monkeypatch):
    monkeypatch.setattr(ui, "get_query_value", lambda key: "logs")
    ui.st.session_state.current_tab = "portfolio"
    assert ui.get_current_tab() == "logs"
    assert ui.st.session_state.current_tab == "logs"


def test_set_current_tab_invalid_fallback(monkeypatch):
    captured: dict[str, str] = {}
    monkeypatch.setattr(ui, "set_query_value", lambda key, value: captured.update({key: value}))
    ui.set_current_tab("invalid")
    assert ui.st.session_state.current_tab == "portfolio"
    assert captured["tab"] == "portfolio"
