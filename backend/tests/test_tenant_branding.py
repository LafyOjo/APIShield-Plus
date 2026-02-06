import os
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./branding_test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("SKIP_MIGRATIONS", "1")

from app.main import app  # noqa: E402
import app.core.db as db_module  # noqa: E402
import app.core.access_log as access_log_module  # noqa: E402
import app.core.policy as policy_module  # noqa: E402
from app.core.db import Base  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402
from app.crud.tenants import create_tenant, create_tenant_with_owner  # noqa: E402
from app.crud.users import create_user  # noqa: E402
from app.models.plans import Plan  # noqa: E402


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


def _seed_free_plan(db):
    plan = Plan(
        name="Free",
        price_monthly=0,
        limits_json={"websites": 1},
        features_json={},
        is_active=True,
    )
    db.add(plan)
    db.commit()
    return plan


def _login(username: str) -> str:
    resp = client.post("/login", json={"username": username, "password": "pw"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_white_label_branding_mode_enforced_by_plan():
    db_url = f"sqlite:///./branding_plan_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        _seed_free_plan(db)
        owner = create_user(db, username="owner", password_hash=get_password_hash("pw"))
        tenant, _ = create_tenant_with_owner(db, name="Brand Tenant", slug=None, owner_user=owner)
        db.commit()
        tenant_slug = tenant.slug

    token = _login("owner")
    resp = client.patch(
        "/api/v1/branding",
        json={
            "is_enabled": True,
            "badge_branding_mode": "white_label",
            "custom_domain": "brand.example.com",
            "brand_name": "BrandCo",
        },
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["badge_branding_mode"] == "your_brand"
    assert data["is_enabled"] is False
    assert data["custom_domain"] is None


def test_branding_changes_scoped_to_tenant_only():
    db_url = f"sqlite:///./branding_scope_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        _seed_free_plan(db)
        owner = create_user(db, username="owner2", password_hash=get_password_hash("pw"))
        tenant, _ = create_tenant_with_owner(db, name="Tenant A", slug=None, owner_user=owner)
        other = create_tenant(db, name="Tenant B")
        tenant_slug = tenant.slug
        other_slug = other.slug

    token = _login("owner2")
    resp = client.get(
        "/api/v1/branding",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": other_slug},
    )
    assert resp.status_code == 404

    resp_ok = client.get(
        "/api/v1/branding",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp_ok.status_code == 200
