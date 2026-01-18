import os
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("SKIP_MIGRATIONS", "1")

from app.main import app
import app.core.db as db_module
import app.core.access_log as access_log_module
import app.core.policy as policy_module
from app.core.config import settings
from app.core.db import Base
from app.core.security import get_password_hash
from app.crud.memberships import create_membership
from app.crud.tenants import create_tenant
from app.crud.users import create_user
from app.crud.websites import create_website
from app.models.enums import RoleEnum


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


def test_create_environment_requires_admin_or_owner():
    db_url = f"sqlite:///./env_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="env-owner", password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name="EnvTenant")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=owner.id,
            role="owner",
            created_by_user_id=owner.id,
        )
        viewer = create_user(db, username="env-viewer", password_hash=get_password_hash("pw"), role="user")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=viewer.id,
            role=RoleEnum.VIEWER,
            created_by_user_id=owner.id,
        )
        website = create_website(db, tenant.id, "env.example.com", created_by_user_id=owner.id)
        tenant_slug = tenant.slug
        website_id = website.id

    token = _login("env-viewer")
    resp = client.post(
        f"/api/v1/websites/{website_id}/environments",
        json={"name": "staging"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    expected = 404 if settings.TENANT_STRICT_404 else 403
    assert resp.status_code == expected


def test_create_environment_cross_tenant_website_rejected():
    db_url = f"sqlite:///./env_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        user = create_user(db, username="env-cross", password_hash=get_password_hash("pw"), role="user")
        tenant_a = create_tenant(db, name="EnvTenantA")
        tenant_b = create_tenant(db, name="EnvTenantB")
        create_membership(
            db,
            tenant_id=tenant_a.id,
            user_id=user.id,
            role="owner",
            created_by_user_id=user.id,
        )
        create_membership(
            db,
            tenant_id=tenant_b.id,
            user_id=user.id,
            role="owner",
            created_by_user_id=user.id,
        )
        website = create_website(db, tenant_b.id, "envb.example.com", created_by_user_id=user.id)
        tenant_a_slug = tenant_a.slug
        website_id = website.id

    token = _login("env-cross")
    resp = client.post(
        f"/api/v1/websites/{website_id}/environments",
        json={"name": "staging"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_a_slug},
    )
    assert resp.status_code == 404


def test_create_environment_duplicate_name_rejected():
    db_url = f"sqlite:///./env_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="env-dup", password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name="EnvDupTenant")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=owner.id,
            role="owner",
            created_by_user_id=owner.id,
        )
        website = create_website(db, tenant.id, "envdup.example.com", created_by_user_id=owner.id)
        tenant_slug = tenant.slug
        website_id = website.id

    token = _login("env-dup")
    resp = client.post(
        f"/api/v1/websites/{website_id}/environments",
        json={"name": "staging", "base_url": "https://staging.example.com"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "staging"

    resp = client.post(
        f"/api/v1/websites/{website_id}/environments",
        json={"name": "staging"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 409
