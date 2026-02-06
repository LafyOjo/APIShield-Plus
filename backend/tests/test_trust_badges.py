import os
import time
from datetime import datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("INTEGRATION_ENCRYPTION_KEY", "a" * 32)
os.environ.setdefault("ZERO_TRUST_API_KEY", "")
os.environ.setdefault("SKIP_MIGRATIONS", "1")

from app.main import app
import app.core.db as db_module
import app.core.access_log as access_log_module
import app.core.policy as policy_module
from app.core.db import Base
from app.core.security import get_password_hash
from app.core.badges import extract_badge_key, sign_badge_request
from app.crud.memberships import create_membership
from app.crud.tenants import create_tenant
from app.crud.trust_badges import get_or_create_badge_config
from app.crud.users import create_user
from app.crud.website_environments import list_environments
from app.crud.websites import create_website
from app.models.enums import RoleEnum
from app.models.trust_scoring import TrustSnapshot


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


def _setup_env(SessionLocal, *, username: str, tenant_name: str):
    with SessionLocal() as db:
        owner = create_user(db, username=username, password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name=tenant_name)
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=owner.id,
            role=RoleEnum.OWNER,
            created_by_user_id=owner.id,
        )
        website = create_website(db, tenant.id, f"{tenant.slug}.example.com", created_by_user_id=owner.id)
        env = list_environments(db, website.id)[0]
        db.commit()
        return tenant.slug, tenant.id, website.id, env.id


def test_badge_public_js_serves_with_cache_headers():
    db_url = f"sqlite:///./badge_js_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    _tenant_slug, tenant_id, website_id, _env_id = _setup_env(
        SessionLocal, username="badge-js", tenant_name="BadgeJS"
    )
    with SessionLocal() as db:
        config = get_or_create_badge_config(db, tenant_id, website_id)
        config.is_enabled = True
        db.commit()

    resp = client.get(f"/public/badge.js?website_id={website_id}")
    assert resp.status_code == 200
    assert "application/javascript" in resp.headers.get("content-type", "")
    assert "max-age" in resp.headers.get("cache-control", "")
    assert resp.headers.get("etag")


def test_badge_data_requires_valid_signature():
    db_url = f"sqlite:///./badge_data_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    _tenant_slug, tenant_id, website_id, env_id = _setup_env(
        SessionLocal, username="badge-data", tenant_name="BadgeData"
    )
    with SessionLocal() as db:
        config = get_or_create_badge_config(db, tenant_id, website_id)
        config.is_enabled = True
        db.add(
            TrustSnapshot(
                tenant_id=tenant_id,
                website_id=website_id,
                environment_id=env_id,
                bucket_start=datetime.utcnow(),
                path=None,
                trust_score=92,
                confidence=0.9,
            )
        )
        db.commit()
        key = extract_badge_key(config)

    ts = int(time.time())
    sig = sign_badge_request(website_id, ts, key)

    resp = client.get(f"/public/badge/data?website_id={website_id}&ts={ts}&sig=invalid")
    assert resp.status_code == 403

    resp = client.get(f"/public/badge/data?website_id={website_id}&ts={ts}&sig={sig}")
    assert resp.status_code == 200
    assert resp.headers.get("etag")
    payload = resp.json()
    assert payload["trust_score"] == 92


def test_badge_free_plan_forces_branding_enabled():
    db_url = f"sqlite:///./badge_policy_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_slug, _tenant_id, website_id, _env_id = _setup_env(
        SessionLocal, username="badge-policy", tenant_name="BadgePolicy"
    )

    token = _login("badge-policy")
    resp = client.post(
        "/api/v1/badges/config",
        json={
            "website_id": website_id,
            "is_enabled": True,
            "style": "dark",
            "show_branding": False,
        },
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["show_branding"] is True
    assert payload["style"] == "light"
