from app.services import AuthService


def test_register_login_and_token_roundtrip():
    svc = AuthService()
    svc.ensure_admin_user()

    ok, _ = svc.register("alice", "p@ss")
    assert ok is True

    assert svc.login("alice", "p@ss") is True
    assert svc.login("alice", "wrong") is False

    token = svc.make_token("alice")
    assert svc.parse_token(token) == "alice"
