import os

import pytest
from fastapi.testclient import TestClient
from pathlib import Path
from uuid import uuid4

# Ensure required settings exist before app import.
os.environ.setdefault("SKIP_MIGRATIONS", "1")
os.environ.setdefault("DATABASE_URL", "sqlite:///./tenant_test.db")
os.environ.setdefault("SECRET_KEY", "secret")

from app.main import app
from app.api.dependencies import get_current_user, get_db
from app.core.config import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.core.db as db_module
from app.core.db import Base
from app.models import alerts, audit_logs, access_logs, auth_events, events, policies, users  # noqa: F401
from app.core.security import get_password_hash
from app.crud.tenants import create_tenant
from app.crud.memberships import create_membership
from app.crud.users import create_user
import app.core.access_log as access_log_module
import app.core.policy as policy_module


@pytest.fixture(autouse=True)
def override_dependencies():
    db_url = f"sqlite:///./tenant_test_{uuid4().hex}.db"
    os.environ["DATABASE_URL"] = db_url

    test_engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        future=True,
    )
    TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False, future=True)
    db_module.engine = test_engine
    db_module.SessionLocal = TestSessionLocal
    access_log_module.SessionLocal = TestSessionLocal
    policy_module.SessionLocal = TestSessionLocal
    access_log_module.create_access_log = lambda db, username, path: None

    async def fake_db():
        with TestSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = fake_db
    Base.metadata.create_all(bind=test_engine)
    with TestSessionLocal() as session:
        owner = create_user(session, username="owner", password_hash=get_password_hash("pw"), role="user")
        user = create_user(session, username="alice", password_hash=get_password_hash("pw"), role="admin")
        admin_user_id = user.id
        tenant = create_tenant(session, name="Tenant One", slug="t1")
        create_membership(
            session,
            tenant_id=tenant.id,
            user_id=owner.id,
            role="owner",
            created_by_user_id=owner.id,
        )
        create_membership(
            session,
            tenant_id=tenant.id,
            user_id=user.id,
            role="admin",
            created_by_user_id=user.id,
        )

    async def fake_user():
        return type("User", (), {"id": admin_user_id, "username": "alice", "role": "admin"})

    app.dependency_overrides[get_current_user] = fake_user
    yield
    app.dependency_overrides.clear()


def test_request_without_tenant_header_rejected_for_tenant_scoped_routes():
    client = TestClient(app)
    resp = client.get("/config")
    assert resp.status_code == 400


def test_config_route_allows_admin_with_tenant():
    client = TestClient(app)
    resp = client.get("/config", headers={"X-Tenant-ID": "t1"})
    assert resp.status_code == 200
    assert "fail_limit" in resp.json()


def test_request_with_tenant_header_validates_membership():
    async def fake_user():
        return type("User", (), {"id": 9999, "username": "outsider", "role": "admin"})

    app.dependency_overrides[get_current_user] = fake_user
    client = TestClient(app)
    resp = client.get("/config", headers={"X-Tenant-ID": "t1"})
    expected = 404 if settings.TENANT_STRICT_404 else 403
    assert resp.status_code == expected
