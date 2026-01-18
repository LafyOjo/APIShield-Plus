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
from app.crud.websites import create_website
from app.models.project_tags import ProjectTag, WebsiteTag


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


def test_create_tag_unique_per_tenant():
    db_url = f"sqlite:///./tags_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="owner", password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name="Acme")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=owner.id,
            role="owner",
            created_by_user_id=owner.id,
        )
        tenant_slug = tenant.slug

    token = _login("owner")
    resp = client.post(
        "/api/v1/tags",
        json={"name": "Marketing", "color": "#ff00aa"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200

    dup = client.post(
        "/api/v1/tags",
        json={"name": "Marketing"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert dup.status_code == 400


def test_attach_and_detach_tags():
    db_url = f"sqlite:///./tags_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="owner2", password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name="Umbrella")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=owner.id,
            role="owner",
            created_by_user_id=owner.id,
        )
        website = create_website(db, tenant.id, "umbrella.com")
        tag = ProjectTag(tenant_id=tenant.id, name="Checkout")
        db.add(tag)
        db.commit()
        db.refresh(tag)
        tenant_slug = tenant.slug
        website_id = website.id
        tag_id = tag.id

    token = _login("owner2")
    attach = client.post(
        f"/api/v1/websites/{website_id}/tags/{tag_id}",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert attach.status_code == 200

    with SessionLocal() as db:
        link = (
            db.query(WebsiteTag)
            .filter(WebsiteTag.website_id == website_id, WebsiteTag.tag_id == tag_id)
            .first()
        )
        assert link is not None

    detach = client.delete(
        f"/api/v1/websites/{website_id}/tags/{tag_id}",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert detach.status_code == 200

    with SessionLocal() as db:
        link = (
            db.query(WebsiteTag)
            .filter(WebsiteTag.website_id == website_id, WebsiteTag.tag_id == tag_id)
            .first()
        )
        assert link is None


def test_cross_tenant_access_blocked():
    db_url = f"sqlite:///./tags_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="owner3", password_hash=get_password_hash("pw"), role="user")
        tenant_a = create_tenant(db, name="TenantA")
        tenant_b = create_tenant(db, name="TenantB")
        create_membership(
            db,
            tenant_id=tenant_a.id,
            user_id=owner.id,
            role="owner",
            created_by_user_id=owner.id,
        )
        website = create_website(db, tenant_b.id, "tenantb.com")
        tag = ProjectTag(tenant_id=tenant_b.id, name="Secret")
        db.add(tag)
        db.commit()
        db.refresh(tag)
        tenant_a_slug = tenant_a.slug
        website_id = website.id
        tag_id = tag.id

    token = _login("owner3")
    resp = client.post(
        f"/api/v1/websites/{website_id}/tags/{tag_id}",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_a_slug},
    )
    assert resp.status_code == 404
