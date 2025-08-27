import importlib
import os

os.environ['DATABASE_URL'] = 'sqlite:///./test.db'
os.environ['SECRET_KEY'] = 'test-secret'

from fastapi.testclient import TestClient  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402
from app.crud.users import create_user  # noqa: E402


def _reload_app():
    import app.core.re_auth
    import app.main
    importlib.reload(app.core.re_auth)
    importlib.reload(app.main)
    return TestClient(app.main.app)


def setup_function(_):
    with SessionLocal() as db:
        create_user(db, username="alice", password_hash=get_password_hash("pw"))


def test_missing_password_header(monkeypatch):
    monkeypatch.setenv("REAUTH_PER_REQUEST", "true")
    client = _reload_app()

    token = (
        client.post(
            "/login",
            json={"username": "alice", "password": "pw"},
        ).json()["access_token"]
    )
    resp = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Password required"

    monkeypatch.setenv("REAUTH_PER_REQUEST", "false")
    _reload_app()


def test_reauth_success(monkeypatch):
    monkeypatch.setenv("REAUTH_PER_REQUEST", "true")
    client = _reload_app()

    token = (
        client.post(
            "/login",
            json={"username": "alice", "password": "pw"},
        ).json()["access_token"]
    )
    headers = {"Authorization": f"Bearer {token}", "X-Reauth-Password": "pw"}
    resp = client.get("/api/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["username"] == "alice"

    monkeypatch.setenv("REAUTH_PER_REQUEST", "false")
    _reload_app()
