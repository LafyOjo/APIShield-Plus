import os
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")

from app.core.db import Base
from app.core.entitlements import invalidate_entitlement_cache
from app.crud.subscriptions import upsert_stripe_subscription, set_tenant_plan
from app.crud.tenants import create_tenant
from app.entitlements.resolver import resolve_entitlements_for_tenant
from app.models.plans import Plan


def _setup_db(db_url: str):
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        future=True,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    return SessionLocal


def test_entitlements_free_plan_limits_and_features():
    db_url = f"sqlite:///./entitlements_free_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        free_plan = Plan(
            name="Free",
            price_monthly=0,
            limits_json={"websites": 1, "geo_history_days": 1, "notification_rules": 1},
            features_json={"geo_map": False, "advanced_alerting": False},
            is_active=True,
        )
        db.add(free_plan)
        db.commit()
        tenant = create_tenant(db, name="FreeCo")

        invalidate_entitlement_cache(tenant.id)
        entitlements = resolve_entitlements_for_tenant(db, tenant.id, use_cache=False)
        assert entitlements["features"]["geo_map"] is False
        assert entitlements["limits"]["websites"] == 1
        assert entitlements["limits"]["notification_rules"] == 1


def test_entitlements_pro_plan_enables_geo_map_and_more_rules():
    db_url = f"sqlite:///./entitlements_pro_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        free_plan = Plan(
            name="Free",
            price_monthly=0,
            limits_json={"websites": 1, "notification_rules": 1},
            features_json={"geo_map": False, "advanced_alerting": False},
            is_active=True,
        )
        pro_plan = Plan(
            name="Pro",
            price_monthly=149,
            limits_json={"websites": 10, "notification_rules": 10},
            features_json={"geo_map": True, "advanced_alerting": True},
            is_active=True,
        )
        db.add_all([free_plan, pro_plan])
        db.commit()
        tenant = create_tenant(db, name="ProCo")
        set_tenant_plan(db, tenant.id, pro_plan.id)

        invalidate_entitlement_cache(tenant.id)
        entitlements = resolve_entitlements_for_tenant(db, tenant.id, use_cache=False)
        assert entitlements["features"]["geo_map"] is True
        assert entitlements["limits"]["websites"] == 10
        assert entitlements["limits"]["notification_rules"] == 10


def test_entitlements_cache_invalidated_on_subscription_update():
    db_url = f"sqlite:///./entitlements_cache_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        free_plan = Plan(
            name="Free",
            price_monthly=0,
            limits_json={"websites": 1},
            features_json={"geo_map": False},
            is_active=True,
        )
        pro_plan = Plan(
            name="Pro",
            price_monthly=149,
            limits_json={"websites": 10},
            features_json={"geo_map": True},
            is_active=True,
        )
        db.add_all([free_plan, pro_plan])
        db.commit()
        tenant = create_tenant(db, name="CacheCo")

        invalidate_entitlement_cache(tenant.id)
        entitlements = resolve_entitlements_for_tenant(db, tenant.id, use_cache=True)
        assert entitlements["features"]["geo_map"] is False

        upsert_stripe_subscription(
            db,
            tenant_id=tenant.id,
            plan=pro_plan,
            plan_key="pro",
            stripe_customer_id="cus_test",
            stripe_subscription_id="sub_test",
            status="active",
        )

        entitlements = resolve_entitlements_for_tenant(db, tenant.id, use_cache=True)
        assert entitlements["features"]["geo_map"] is True
