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
from app.core.db import Base
from app.core.security import get_password_hash
from app.crud.users import create_user
from app.crud.tenants import create_tenant_with_owner
from app.crud.memberships import create_membership
from app.models.data_retention import DataRetentionPolicy
from app.models.feature_entitlements import FeatureEntitlement
from app.models.memberships import Membership
from app.models.enums import RoleEnum
from app.models.plans import Plan
from app.models.subscriptions import Subscription
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


def test_create_tenant_endpoint_creates_owner_membership():
    db_url = f"sqlite:///./tenants_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        _seed_free_plan(db)
        user = create_user(db, username="owner", password_hash=get_password_hash("pw"))
        user_id = user.id

    token = _login("owner")
    resp = client.post(
        "/api/v1/tenants",
        json={"name": "Acme Workspace"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    tenant_id = payload["tenant"]["id"]

    with SessionLocal() as db:
        membership = (
            db.query(Membership)
            .filter(Membership.tenant_id == tenant_id, Membership.user_id == user_id)
            .first()
        )
        assert membership is not None
        assert membership.role == RoleEnum.OWNER


def test_create_tenant_slug_collision_handled():
    db_url = f"sqlite:///./tenants_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        _seed_free_plan(db)
        create_user(db, username="owner2", password_hash=get_password_hash("pw"))

    token = _login("owner2")
    first = client.post(
        "/api/v1/tenants",
        json={"name": "Acme", "slug": "acme"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first.status_code == 200
    second = client.post(
        "/api/v1/tenants",
        json={"name": "Acme", "slug": "acme"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert second.status_code == 200
    assert first.json()["tenant"]["slug"] != second.json()["tenant"]["slug"]


def test_create_tenant_provisions_defaults():
    db_url = f"sqlite:///./tenants_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        _seed_free_plan(db)
        create_user(db, username="owner3", password_hash=get_password_hash("pw"))

    token = _login("owner3")
    resp = client.post(
        "/api/v1/tenants",
        json={"name": "Defaults Inc"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    tenant_id = resp.json()["tenant"]["id"]

    with SessionLocal() as db:
        settings_row = (
            db.query(TenantSettings)
            .filter(TenantSettings.tenant_id == tenant_id)
            .first()
        )
        assert settings_row is not None
        policies = (
            db.query(DataRetentionPolicy)
            .filter(DataRetentionPolicy.tenant_id == tenant_id)
            .all()
        )
        assert policies
        subscription = (
            db.query(Subscription)
            .filter(Subscription.tenant_id == tenant_id)
            .first()
        )
        assert subscription is not None
        entitlements = (
            db.query(FeatureEntitlement)
            .filter(FeatureEntitlement.tenant_id == tenant_id)
            .all()
        )
        assert entitlements


def test_list_tenants_returns_only_user_memberships():
    db_url = f"sqlite:///./tenants_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        _seed_free_plan(db)
        user = create_user(db, username="user1", password_hash=get_password_hash("pw"))
        other_user = create_user(db, username="user2", password_hash=get_password_hash("pw"))
        tenant, _ = create_tenant_with_owner(
            db,
            name="User One",
            slug=None,
            owner_user=user,
        )
        create_tenant_with_owner(
            db,
            name="Other Tenant",
            slug=None,
            owner_user=other_user,
        )
        db.commit()
        tenant_id = tenant.id

    token = _login("user1")
    resp = client.get(
        "/api/v1/tenants",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload) == 1
    assert payload[0]["id"] == tenant_id


def test_list_tenants_excludes_deleted_tenants():
    db_url = f"sqlite:///./tenants_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        _seed_free_plan(db)
        user = create_user(db, username="deleteme", password_hash=get_password_hash("pw"))
        active, _ = create_tenant_with_owner(
            db,
            name="Active Tenant",
            slug=None,
            owner_user=user,
        )
        deleted, _ = create_tenant_with_owner(
            db,
            name="Deleted Tenant",
            slug=None,
            owner_user=user,
        )
        deleted.deleted_at = deleted.updated_at
        db.commit()
        active_id = active.id

    token = _login("deleteme")
    resp = client.get(
        "/api/v1/tenants",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert [item["id"] for item in payload] == [active_id]


def test_list_tenants_includes_role():
    db_url = f"sqlite:///./tenants_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        _seed_free_plan(db)
        user = create_user(db, username="member", password_hash=get_password_hash("pw"))
        owner = create_user(db, username="owner", password_hash=get_password_hash("pw"))
        owner_tenant, _ = create_tenant_with_owner(
            db,
            name="Owner Tenant",
            slug=None,
            owner_user=user,
        )
        other_tenant, _ = create_tenant_with_owner(
            db,
            name="Shared Tenant",
            slug=None,
            owner_user=owner,
        )
        create_membership(
            db,
            tenant_id=other_tenant.id,
            user_id=user.id,
            role=RoleEnum.ANALYST,
            created_by_user_id=owner.id,
        )
        db.commit()
        owner_slug = owner_tenant.slug
        other_slug = other_tenant.slug

    token = _login("member")
    resp = client.get(
        "/api/v1/tenants",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert [item["role"] for item in payload] == [RoleEnum.OWNER, RoleEnum.ANALYST]
    assert {item["slug"] for item in payload} == {owner_slug, other_slug}


def test_switch_tenant_requires_membership():
    db_url = f"sqlite:///./tenants_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        _seed_free_plan(db)
        member = create_user(db, username="switcher", password_hash=get_password_hash("pw"))
        outsider = create_user(db, username="outsider", password_hash=get_password_hash("pw"))
        tenant, _ = create_tenant_with_owner(
            db,
            name="Member Tenant",
            slug=None,
            owner_user=member,
        )
        outsider_tenant, _ = create_tenant_with_owner(
            db,
            name="Outsider Tenant",
            slug=None,
            owner_user=outsider,
        )
        db.commit()
        outsider_tenant_id = outsider_tenant.id

    token = _login("switcher")
    resp = client.post(
        f"/api/v1/tenants/{outsider_tenant_id}/switch",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_switch_tenant_returns_entitlements_and_settings():
    db_url = f"sqlite:///./tenants_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        _seed_free_plan(db)
        user = create_user(db, username="entitled", password_hash=get_password_hash("pw"))
        tenant, _ = create_tenant_with_owner(
            db,
            name="Entitlements Tenant",
            slug=None,
            owner_user=user,
        )
        db.commit()
        tenant_id = tenant.id

    token = _login("entitled")
    resp = client.post(
        f"/api/v1/tenants/{tenant_id}/switch",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["tenant"]["id"] == tenant_id
    assert payload["role"] == RoleEnum.OWNER
    assert "features" in payload["entitlements"]
    assert "limits" in payload["entitlements"]
    assert payload["settings"]["timezone"] == "UTC"


def test_switch_deleted_tenant_rejected():
    db_url = f"sqlite:///./tenants_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        _seed_free_plan(db)
        user = create_user(db, username="deleted", password_hash=get_password_hash("pw"))
        tenant, _ = create_tenant_with_owner(
            db,
            name="Deleted Tenant",
            slug=None,
            owner_user=user,
        )
        tenant.deleted_at = tenant.updated_at
        db.commit()
        tenant_id = tenant.id

    token = _login("deleted")
    resp = client.post(
        f"/api/v1/tenants/{tenant_id}/switch",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
