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
from app.core.verification import generate_verification_token
from app.crud.memberships import create_membership
from app.crud.tenants import create_tenant
from app.crud.users import create_user
from app.crud.websites import create_website
from app.models.domain_verification import DomainVerification


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


def test_start_verification_creates_pending_record():
    db_url = f"sqlite:///./verify_{uuid4().hex}.db"
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
        website = create_website(db, tenant.id, "acme.com")
        tenant_slug = tenant.slug
        website_id = website.id
        owner_id = owner.id

    token = _login("owner")
    resp = client.post(
        f"/api/v1/websites/{website_id}/verify/start",
        json={"method": "meta_tag"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "pending"
    assert payload["method"] == "meta_tag"
    assert "token" in payload

    with SessionLocal() as db:
        record = (
            db.query(DomainVerification)
            .filter(DomainVerification.website_id == website_id)
            .first()
        )
        assert record is not None
        assert record.token == payload["token"]
        assert record.status == "pending"
        assert record.created_by_user_id == owner_id


def test_cannot_start_verification_for_other_tenant_website():
    db_url = f"sqlite:///./verify_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="owner2", password_hash=get_password_hash("pw"), role="user")
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
        tenant_a_slug = tenant_a.slug
        website_id = website.id

    token = _login("owner2")
    resp = client.post(
        f"/api/v1/websites/{website_id}/verify/start",
        json={"method": "meta_tag"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_a_slug},
    )
    assert resp.status_code == 404


def test_status_returns_latest_state():
    db_url = f"sqlite:///./verify_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="owner3", password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name="Umbrella")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=owner.id,
            role="owner",
            created_by_user_id=owner.id,
        )
        website = create_website(db, tenant.id, "umbrella.com")
        tenant_slug = tenant.slug
        website_id = website.id

    token = _login("owner3")
    start = client.post(
        f"/api/v1/websites/{website_id}/verify/start",
        json={"method": "well_known"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert start.status_code == 200

    resp = client.get(
        f"/api/v1/websites/{website_id}/verify/status",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "pending"
    assert payload["method"] == "well_known"


def test_token_uniqueness_basic():
    token_one = generate_verification_token()
    token_two = generate_verification_token()
    assert token_one != token_two
