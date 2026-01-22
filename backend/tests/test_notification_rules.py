import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("INTEGRATION_ENCRYPTION_KEY", "a" * 32)
os.environ["SKIP_MIGRATIONS"] = "1"

from app.core.db import Base
from app.crud.notification_channels import create_channel
from app.crud.notification_rules import create_rule
from app.entitlements.enforcement import PlanLimitExceeded
from app.crud.subscriptions import set_tenant_plan
from app.crud.tenants import create_tenant
from app.models.plans import Plan
from app.models.notification_rules import NotificationRuleChannel


def _setup_db(db_url: str):
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        future=True,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    return SessionLocal


def test_notification_rule_validation_rejects_invalid_thresholds():
    db_url = f"sqlite:///./notification_rules_invalid_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        tenant = create_tenant(db, name="Acme")
        with pytest.raises(ValueError):
            create_rule(
                db,
                tenant_id=tenant.id,
                name="Login failures",
                trigger_type="login_fail_spike",
                thresholds_json={},
            )


def test_notification_rule_channel_links_tenant_scoped():
    db_url = f"sqlite:///./notification_rules_links_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        tenant_a = create_tenant(db, name="Wayne")
        tenant_b = create_tenant(db, name="Stark")
        channel = create_channel(
            db,
            tenant_id=tenant_a.id,
            channel_type="slack",
            name="Ops Slack",
            config_public={"channel": "#ops"},
            config_secret={"token": "secret"},
        )
        rule = create_rule(
            db,
            tenant_id=tenant_a.id,
            name="Incident created",
            trigger_type="incident_created",
            route_to_channel_ids=[channel.id],
        )
        link = (
            db.query(NotificationRuleChannel)
            .filter(NotificationRuleChannel.rule_id == rule.id)
            .first()
        )
        assert link is not None
        with pytest.raises(ValueError):
            create_rule(
                db,
                tenant_id=tenant_b.id,
                name="Incident created",
                trigger_type="incident_created",
                route_to_channel_ids=[channel.id],
            )


def test_notification_rule_limit_enforced_by_entitlement():
    db_url = f"sqlite:///./notification_rules_limit_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        plan = Plan(
            name="Basic",
            price_monthly=10,
            limits_json={"notification_rules": 1},
            features_json={},
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)
        tenant = create_tenant(db, name="Umbrella")
        set_tenant_plan(db, tenant.id, plan.id)

        create_rule(
            db,
            tenant_id=tenant.id,
            name="Incident created",
            trigger_type="incident_created",
        )
        with pytest.raises(PlanLimitExceeded):
            create_rule(
                db,
                tenant_id=tenant.id,
                name="Another rule",
                trigger_type="incident_created",
            )
