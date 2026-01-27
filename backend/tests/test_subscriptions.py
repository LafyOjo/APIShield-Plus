import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "secret")

from app.core.db import Base
from app.crud.subscriptions import (
    cancel_subscription_stub,
    get_active_subscription_for_tenant,
    set_tenant_plan,
)
from app.crud.tenants import create_tenant
from app.models.plans import Plan
from app.models.subscriptions import Subscription


@pytest.fixture
def db_session(tmp_path):
    db_url = f"sqlite:///{tmp_path}/subscriptions_test.db"
    os.environ["DATABASE_URL"] = db_url
    os.environ["SKIP_MIGRATIONS"] = "1"
    engine = create_engine(db_url, future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    with TestingSessionLocal() as session:
        yield session


def create_plan(db_session, name="Free"):
    plan = Plan(
        name=name,
        price_monthly=0,
        limits_json={"websites": 1},
        features_json={"heatmaps": False},
        is_active=True,
    )
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    return plan


def test_create_subscription_links_tenant_to_plan(db_session):
    tenant = create_tenant(db_session, name="Acme")
    plan = create_plan(db_session, name="Free")

    subscription = set_tenant_plan(db_session, tenant_id=tenant.id, plan_id=plan.id)

    assert isinstance(subscription, Subscription)
    assert subscription.tenant_id == tenant.id
    assert subscription.plan_id == plan.id
    assert subscription.status == "active"


def test_get_active_subscription_for_tenant_returns_expected(db_session):
    tenant = create_tenant(db_session, name="Umbrella")
    plan = create_plan(db_session, name="Pro")
    subscription = set_tenant_plan(db_session, tenant_id=tenant.id, plan_id=plan.id)

    found = get_active_subscription_for_tenant(db_session, tenant.id)

    assert found is not None
    assert found.id == subscription.id


def test_subscription_status_transitions_stub(db_session):
    tenant = create_tenant(db_session, name="Wayne")
    plan = create_plan(db_session, name="Pro")
    subscription = set_tenant_plan(db_session, tenant_id=tenant.id, plan_id=plan.id)

    canceled = cancel_subscription_stub(db_session, subscription.id, cancel_at_period_end=True)

    assert canceled is not None
    assert canceled.status == "canceled"
    assert canceled.cancel_at_period_end is True
