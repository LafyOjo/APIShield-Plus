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
from app.core.config import settings
from app.core.security import get_password_hash
from app.crud.memberships import create_membership
from app.crud.tenant_settings import update_settings
from app.crud.tenants import create_tenant
from app.crud.users import create_user


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


def test_config_uses_tenant_defaults():
    db_url = f"sqlite:///./config_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        user = create_user(db, username="admin", password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name="Acme")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=user.id,
            role="admin",
            created_by_user_id=user.id,
        )
        tenant_slug = tenant.slug

    token = _login("admin")
    resp = client.get(
        "/api/v1/config",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    assert resp.json()["fail_limit"] == settings.FAIL_LIMIT


def test_config_reads_tenant_override():
    db_url = f"sqlite:///./config_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        user = create_user(db, username="admin2", password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name="Umbrella")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=user.id,
            role="admin",
            created_by_user_id=user.id,
        )
        update_settings(db, tenant.id, {"alert_prefs": {"fail_limit": 9}})
        tenant_slug = tenant.slug

    token = _login("admin2")
    resp = client.get(
        "/api/v1/config",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    assert resp.json()["fail_limit"] == 9
