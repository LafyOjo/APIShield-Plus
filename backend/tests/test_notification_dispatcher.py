import os
from datetime import datetime, timedelta, timezone
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
from app.crud.tenants import create_tenant
from app.models.incidents import Incident
from app.models.notification_deliveries import NotificationDelivery
from app.notifications.dispatcher import dispatch


def _setup_db(db_url: str):
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        future=True,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    return SessionLocal


def _seed_incident(db, tenant_id: int) -> Incident:
    now = datetime.now(timezone.utc)
    incident = Incident(
        tenant_id=tenant_id,
        website_id=None,
        environment_id=None,
        status="open",
        category="login",
        title="Login spike",
        summary=None,
        severity="high",
        first_seen_at=now - timedelta(minutes=10),
        last_seen_at=now,
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident


def test_dispatcher_creates_deliveries_for_matching_rules():
    db_url = f"sqlite:///./notification_dispatch_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        tenant = create_tenant(db, name="Acme")
        channel = create_channel(
            db,
            tenant_id=tenant.id,
            channel_type="slack",
            name="Ops Slack",
            config_public={"channel": "#ops"},
            config_secret={"token": "secret"},
        )
        create_rule(
            db,
            tenant_id=tenant.id,
            name="Incident created",
            trigger_type="incident_created",
            route_to_channel_ids=[channel.id],
        )
        incident = _seed_incident(db, tenant.id)

        deliveries = dispatch(
            db,
            event_type="incident_created",
            tenant_id=tenant.id,
            context_obj=incident,
        )
        assert len(deliveries) == 1
        assert deliveries[0].status == "queued"
        assert deliveries[0].payload_json["type"] == "incident"


def test_dispatcher_respects_cooldown_dedupe():
    db_url = f"sqlite:///./notification_dispatch_dedupe_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        tenant = create_tenant(db, name="Umbrella")
        channel = create_channel(
            db,
            tenant_id=tenant.id,
            channel_type="slack",
            name="Security Slack",
            config_public={"channel": "#security"},
            config_secret={"token": "secret"},
        )
        create_rule(
            db,
            tenant_id=tenant.id,
            name="Incident created",
            trigger_type="incident_created",
            thresholds_json={"cooldown_seconds": 900},
            route_to_channel_ids=[channel.id],
        )
        incident = _seed_incident(db, tenant.id)

        dispatch(
            db,
            event_type="incident_created",
            tenant_id=tenant.id,
            context_obj=incident,
        )
        dispatch(
            db,
            event_type="incident_created",
            tenant_id=tenant.id,
            context_obj=incident,
        )
        count = (
            db.query(NotificationDelivery)
            .filter(NotificationDelivery.tenant_id == tenant.id)
            .count()
        )
        assert count == 1


def test_dispatcher_respects_quiet_hours_skip():
    db_url = f"sqlite:///./notification_dispatch_quiet_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        tenant = create_tenant(db, name="Wayne")
        channel = create_channel(
            db,
            tenant_id=tenant.id,
            channel_type="slack",
            name="Ops Slack",
            config_public={"channel": "#ops"},
            config_secret={"token": "secret"},
        )
        quiet_hours = {
            "timezone": "UTC",
            "ranges": [{"start": "00:00", "end": "23:59"}],
        }
        create_rule(
            db,
            tenant_id=tenant.id,
            name="Incident created",
            trigger_type="incident_created",
            quiet_hours_json=quiet_hours,
            route_to_channel_ids=[channel.id],
        )
        incident = _seed_incident(db, tenant.id)

        deliveries = dispatch(
            db,
            event_type="incident_created",
            tenant_id=tenant.id,
            context_obj=incident,
        )
        assert deliveries
        assert deliveries[0].status == "skipped"
