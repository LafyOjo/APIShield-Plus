import os
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ["SKIP_MIGRATIONS"] = "1"

from app.main import app  # noqa: E402
import app.core.access_log as access_log_module  # noqa: E402
import app.core.db as db_module  # noqa: E402
from app.core.perf import clear_recent_request_perf_records  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402
from app.crud.users import create_user  # noqa: E402
from app.core.db import Base  # noqa: E402


client = TestClient(app)


def _setup_db(db_url: str):
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        future=True,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db_module.engine = engine
    db_module.SessionLocal = SessionLocal
    Base.metadata.create_all(bind=engine)
    return SessionLocal


def _login(username: str) -> str:
    resp = client.post("/login", json={"username": username, "password": "pw"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_perf_records_require_platform_admin():
    db_url = f"sqlite:///./perf_admin_block_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    original_create_access_log = access_log_module.create_access_log
    access_log_module.create_access_log = lambda db, username, path: None
    clear_recent_request_perf_records()
    try:
        with SessionLocal() as db:
            create_user(db, username="user", password_hash=get_password_hash("pw"), role="user")

        token = _login("user")
        resp = client.get(
            "/api/v1/admin/perf/requests",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403
    finally:
        access_log_module.create_access_log = original_create_access_log


def test_platform_admin_can_view_recent_perf_records():
    db_url = f"sqlite:///./perf_admin_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    original_create_access_log = access_log_module.create_access_log
    access_log_module.create_access_log = lambda db, username, path: None
    clear_recent_request_perf_records()
    try:
        with SessionLocal() as db:
            create_user(
                db,
                username="admin",
                password_hash=get_password_hash("pw"),
                role="user",
                is_platform_admin=True,
            )

        token = _login("admin")
        ping = client.get("/ping", headers={"X-Request-ID": "req-perf-1"})
        assert ping.status_code == 200
        health = client.get("/api/v1/health", headers={"X-Request-ID": "req-perf-2"})
        assert health.status_code == 200

        resp = client.get(
            "/api/v1/admin/perf/requests",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload
        assert len(payload) <= 200
        assert any(
            row.get("request_id") == "req-perf-1" and row.get("path") == "/ping"
            for row in payload
        )
        assert any(
            row.get("request_id") == "req-perf-2" and row.get("path") == "/api/v1/health"
            for row in payload
        )
        expected_keys = {
            "request_id",
            "path",
            "status_code",
            "duration_ms",
            "db_time_ms",
            "db_queries_count",
        }
        forbidden_keys = {"query_fingerprint", "slow_queries", "tenant_id", "user_id"}
        for row in payload:
            assert set(row.keys()) == expected_keys
            assert forbidden_keys.isdisjoint(set(row.keys()))
    finally:
        access_log_module.create_access_log = original_create_access_log
