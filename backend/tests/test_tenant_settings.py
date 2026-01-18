import os
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")

from app.main import app
import app.core.db as db_module
import app.core.access_log as access_log_module
import app.core.policy as policy_module
from app.core.db import Base
from app.core.security import get_password_hash
from app.crud.memberships import create_membership
from app.crud.tenants import create_tenant
from app.crud.users import create_user
from app.models.tenant_settings import TenantSettings


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
    access_log_module.SessionLocal = SessionLocal
    policy_module.SessionLocal = SessionLocal
    access_log_module.create_access_log = lambda db, username, path: None
    Base.metadata.create_all(bind=engine)
    return SessionLocal


def _login(username: str) -> str:
    resp = client.post("/login", json={"username": username, "password": "pw"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_settings_auto_created_for_tenant():
    db_url = f"sqlite:///./settings_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        tenant = create_tenant(db, name="Acme")
        settings_row = (
            db.query(TenantSettings)
            .filter(TenantSettings.tenant_id == tenant.id)
            .first()
        )
        assert settings_row is not None
        assert settings_row.timezone == "UTC"
        assert settings_row.retention_days == 30
        assert settings_row.event_retention_days == 30
        assert settings_row.ip_raw_retention_days == 7


def test_update_settings_requires_admin_or_owner():
    db_url = f"sqlite:///./settings_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="owner", password_hash=get_password_hash("pw"), role="user")
        viewer = create_user(db, username="viewer", password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name="Umbrella")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=owner.id,
            role="owner",
            created_by_user_id=owner.id,
        )
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=viewer.id,
            role="viewer",
            created_by_user_id=owner.id,
        )
        tenant_slug = tenant.slug

    viewer_token = _login("viewer")
    resp = client.patch(
        "/api/v1/settings",
        json={"timezone": "America/New_York"},
        headers={"Authorization": f"Bearer {viewer_token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code in {403, 404}

    owner_token = _login("owner")
    resp = client.patch(
        "/api/v1/settings",
        json={"timezone": "America/New_York", "alert_prefs": {"email_alerts": False}},
        headers={"Authorization": f"Bearer {owner_token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["timezone"] == "America/New_York"
    assert payload["alert_prefs"]["email_alerts"] is False


def test_tenant_settings_scoped_by_membership():
    db_url = f"sqlite:///./settings_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        user = create_user(db, username="alice", password_hash=get_password_hash("pw"), role="user")
        tenant_a = create_tenant(db, name="Alpha")
        tenant_b = create_tenant(db, name="Beta")
        create_membership(
            db,
            tenant_id=tenant_a.id,
            user_id=user.id,
            role="owner",
            created_by_user_id=user.id,
        )
        tenant_b_slug = tenant_b.slug

    token = _login("alice")
    resp = client.get(
        "/api/v1/settings",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_b_slug},
    )
    assert resp.status_code in {403, 404}

    resp = client.patch(
        "/api/v1/settings",
        json={"retention_days": 30},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_b_slug},
    )
    assert resp.status_code in {403, 404}
