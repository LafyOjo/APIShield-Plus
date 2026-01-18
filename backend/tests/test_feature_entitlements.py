import os
from uuid import uuid4

import pytest
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
from app.core.entitlements import get_tenant_plan, resolve_effective_entitlements
from app.core.security import get_password_hash
from app.crud.feature_entitlements import upsert_entitlement
from app.crud.memberships import create_membership
from app.crud.subscriptions import set_tenant_plan
from app.crud.tenants import create_tenant
from app.crud.users import create_user
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


def _login(username: str) -> str:
    resp = client.post("/login", json={"username": username, "password": "pw"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_entitlements_default_equals_plan_features():
    db_url = f"sqlite:///./entitlements_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        plan = Plan(
            name="Starter",
            price_monthly=19,
            limits_json={"websites": 3},
            features_json={"heatmaps": True, "prescriptions": False},
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)
        tenant = create_tenant(db, name="Acme")
        set_tenant_plan(db, tenant.id, plan.id)

        entitlements = resolve_effective_entitlements(db, tenant.id, use_cache=False)
        assert entitlements["features"]["heatmaps"] is True
        assert entitlements["features"]["prescriptions"] is False


def test_entitlements_override_wins():
    db_url = f"sqlite:///./entitlements_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        plan = Plan(
            name="Pro",
            price_monthly=49,
            limits_json={"websites": 10},
            features_json={"heatmaps": True},
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)
        tenant = create_tenant(db, name="Umbrella")
        set_tenant_plan(db, tenant.id, plan.id)
        upsert_entitlement(
            db,
            tenant_id=tenant.id,
            feature="heatmaps",
            enabled=False,
            source="manual_override",
        )

        entitlements = resolve_effective_entitlements(db, tenant.id, use_cache=False)
        assert entitlements["features"]["heatmaps"] is False


def test_unknown_feature_rejected():
    db_url = f"sqlite:///./entitlements_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        tenant = create_tenant(db, name="Wayne")
        with pytest.raises(ValueError):
            upsert_entitlement(
                db,
                tenant_id=tenant.id,
                feature="unknown_feature",
                enabled=True,
                source="manual_override",
            )


def test_get_tenant_plan_returns_free_by_default_if_no_subscription():
    db_url = f"sqlite:///./entitlements_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        db.add(
            Plan(
                name="Free",
                price_monthly=0,
                limits_json={"websites": 1},
                features_json={"heatmaps": False},
            )
        )
        db.commit()
        tenant = create_tenant(db, name="NoSub")
        plan = get_tenant_plan(db, tenant.id)
        assert plan is not None
        assert plan.name == "Free"


def test_entitlements_structure_contains_features_and_limits():
    db_url = f"sqlite:///./entitlements_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        plan = Plan(
            name="Basic",
            price_monthly=5,
            limits_json={"events_per_month": 5000},
            features_json={"heatmaps": True},
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)
        tenant = create_tenant(db, name="Umbrella")
        set_tenant_plan(db, tenant.id, plan.id)

        entitlements = resolve_effective_entitlements(db, tenant.id, use_cache=False)
        assert "features" in entitlements
        assert "limits" in entitlements
        assert entitlements["limits"]["events_per_month"] == 5000


def test_cross_tenant_access_blocked():
    db_url = f"sqlite:///./entitlements_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        user = create_user(db, username="alice", password_hash=get_password_hash("pw"), role="user")
        tenant_a = create_tenant(db, name="TenantA")
        tenant_b = create_tenant(db, name="TenantB")
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
        "/api/v1/entitlements",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_b_slug},
    )
    assert resp.status_code in {403, 404}
