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
from app.crud.tenants import create_tenant_with_owner
from app.crud.users import create_user
from app.models.enums import RoleEnum
from app.models.plans import Plan


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
        features_json={"heatmaps": False},
        is_active=True,
    )
    db.add(plan)
    db.commit()


def _login(username: str) -> str:
    resp = client.post("/login", json={"username": username, "password": "pw"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_me_returns_user_and_memberships():
    db_url = f"sqlite:///./me_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        _seed_free_plan(db)
        user = create_user(db, username="alice", password_hash=get_password_hash("pw"))
        tenant_a, _ = create_tenant_with_owner(
            db,
            name="Alpha",
            slug=None,
            owner_user=user,
        )
        owner = create_user(db, username="bob", password_hash=get_password_hash("pw"))
        tenant_b, _ = create_tenant_with_owner(
            db,
            name="Beta",
            slug=None,
            owner_user=owner,
        )
        create_membership(
            db,
            tenant_id=tenant_b.id,
            user_id=user.id,
            role=RoleEnum.ANALYST,
            created_by_user_id=owner.id,
        )
        db.commit()

    token = _login("alice")
    resp = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["user"]["username"] == "alice"
    roles = {m["role"] for m in payload["memberships"]}
    assert roles == {RoleEnum.OWNER.value, RoleEnum.ANALYST.value}
    assert payload["active_tenant"] is None


def test_me_with_tenant_header_includes_active_tenant_entitlements_settings():
    db_url = f"sqlite:///./me_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        _seed_free_plan(db)
        user = create_user(db, username="carol", password_hash=get_password_hash("pw"))
        tenant, _ = create_tenant_with_owner(
            db,
            name="Gamma",
            slug=None,
            owner_user=user,
        )
        db.commit()
        tenant_slug = tenant.slug
        tenant_id = tenant.id

    token = _login("carol")
    resp = client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["active_tenant"]["id"] == tenant_id
    assert payload["active_role"] == RoleEnum.OWNER.value
    assert payload["entitlements"]["features"] is not None
    assert payload["settings"]["timezone"] == "UTC"


def test_me_with_invalid_tenant_header_returns_safe_error():
    db_url = f"sqlite:///./me_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        _seed_free_plan(db)
        user = create_user(db, username="dave", password_hash=get_password_hash("pw"))
        tenant, _ = create_tenant_with_owner(
            db,
            name="Delta",
            slug=None,
            owner_user=user,
        )
        other_owner = create_user(db, username="erin", password_hash=get_password_hash("pw"))
        other_tenant, _ = create_tenant_with_owner(
            db,
            name="Epsilon",
            slug=None,
            owner_user=other_owner,
        )
        db.commit()
        other_slug = other_tenant.slug

    token = _login("dave")
    resp = client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": other_slug},
    )
    expected = 404 if settings.TENANT_STRICT_404 else 403
    assert resp.status_code == expected
