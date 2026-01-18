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
from app.crud.website_environments import list_environments
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


def test_create_website_requires_admin_or_owner():
    db_url = f"sqlite:///./websites_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="owner-web", password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name="SiteTenant")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=owner.id,
            role="owner",
            created_by_user_id=owner.id,
        )
        viewer = create_user(db, username="viewer-web", password_hash=get_password_hash("pw"), role="user")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=viewer.id,
            role=RoleEnum.VIEWER,
            created_by_user_id=owner.id,
        )
        tenant_slug = tenant.slug

    token = _login("viewer-web")
    resp = client.post(
        "/api/v1/websites",
        json={"domain": "example.com"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    expected = 404 if settings.TENANT_STRICT_404 else 403
    assert resp.status_code == expected


def test_create_website_normalizes_domain_and_creates_production_env():
    db_url = f"sqlite:///./websites_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="owner-domain", password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name="NormalizeTenant")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=owner.id,
            role="owner",
            created_by_user_id=owner.id,
        )
        tenant_slug = tenant.slug

    token = _login("owner-domain")
    resp = client.post(
        "/api/v1/websites",
        json={"domain": "Example.COM", "display_name": "Example"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["domain"] == "example.com"
    website_id = payload["id"]

    with SessionLocal() as db:
        envs = list_environments(db, website_id)
        assert len(envs) == 1
        assert envs[0].name == "production"


def test_create_website_duplicate_domain_same_tenant_rejected():
    db_url = f"sqlite:///./websites_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="owner-dup", password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name="DupTenant")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=owner.id,
            role="owner",
            created_by_user_id=owner.id,
        )
        tenant_slug = tenant.slug

    token = _login("owner-dup")
    resp = client.post(
        "/api/v1/websites",
        json={"domain": "example.com"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    resp = client.post(
        "/api/v1/websites",
        json={"domain": "example.com"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 409


def test_create_website_same_domain_different_tenant_allowed():
    db_url = f"sqlite:///./websites_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="owner-multi", password_hash=get_password_hash("pw"), role="user")
        tenant_a = create_tenant(db, name="Tenant Alpha")
        tenant_b = create_tenant(db, name="Tenant Beta")
        create_membership(
            db,
            tenant_id=tenant_a.id,
            user_id=owner.id,
            role="owner",
            created_by_user_id=owner.id,
        )
        create_membership(
            db,
            tenant_id=tenant_b.id,
            user_id=owner.id,
            role="owner",
            created_by_user_id=owner.id,
        )
        tenant_a_slug = tenant_a.slug
        tenant_b_slug = tenant_b.slug

    token = _login("owner-multi")
    resp = client.post(
        "/api/v1/websites",
        json={"domain": "example.com"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_a_slug},
    )
    assert resp.status_code == 200
    resp = client.post(
        "/api/v1/websites",
        json={"domain": "example.com"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_b_slug},
    )
    assert resp.status_code == 200


def test_list_websites_tenant_scoped():
    db_url = f"sqlite:///./websites_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="owner-list", password_hash=get_password_hash("pw"), role="user")
        tenant_a = create_tenant(db, name="ListTenantA")
        tenant_b = create_tenant(db, name="ListTenantB")
        create_membership(
            db,
            tenant_id=tenant_a.id,
            user_id=owner.id,
            role="owner",
            created_by_user_id=owner.id,
        )
        create_membership(
            db,
            tenant_id=tenant_b.id,
            user_id=owner.id,
            role="owner",
            created_by_user_id=owner.id,
        )
        create_website(db, tenant_a.id, "a.example.com", created_by_user_id=owner.id)
        create_website(db, tenant_b.id, "b.example.com", created_by_user_id=owner.id)
        tenant_a_slug = tenant_a.slug

    token = _login("owner-list")
    resp = client.get(
        "/api/v1/websites",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_a_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    domains = {item["domain"] for item in payload}
    assert domains == {"a.example.com"}


def test_get_website_tenant_scoped_404_cross_tenant():
    db_url = f"sqlite:///./websites_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="owner-detail", password_hash=get_password_hash("pw"), role="user")
        tenant_a = create_tenant(db, name="DetailTenantA")
        tenant_b = create_tenant(db, name="DetailTenantB")
        create_membership(
            db,
            tenant_id=tenant_a.id,
            user_id=owner.id,
            role="owner",
            created_by_user_id=owner.id,
        )
        create_membership(
            db,
            tenant_id=tenant_b.id,
            user_id=owner.id,
            role="owner",
            created_by_user_id=owner.id,
        )
        website = create_website(db, tenant_b.id, "detail.example.com", created_by_user_id=owner.id)
        tenant_a_slug = tenant_a.slug
        website_id = website.id

    token = _login("owner-detail")
    resp = client.get(
        f"/api/v1/websites/{website_id}",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_a_slug},
    )
    assert resp.status_code == 404


def test_list_websites_excludes_deleted_by_default():
    db_url = f"sqlite:///./websites_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="owner-delete", password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name="DeleteTenant")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=owner.id,
            role="owner",
            created_by_user_id=owner.id,
        )
        active = create_website(db, tenant.id, "active.example.com", created_by_user_id=owner.id)
        deleted = create_website(db, tenant.id, "deleted.example.com", created_by_user_id=owner.id)
        deleted.status = "deleted"
        deleted.deleted_at = deleted.created_at
        db.commit()
        tenant_slug = tenant.slug

    token = _login("owner-delete")
    resp = client.get(
        "/api/v1/websites",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    domains = {item["domain"] for item in payload}
    assert domains == {active.domain}
