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
from app.notifications.senders.webhook import _sign_payload
from app.jobs.notification_sender import run_notification_sender


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


def test_notification_worker_sends_slack_delivery(monkeypatch):
    db_url = f"sqlite:///./notification_worker_slack_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        tenant = create_tenant(db, name="Acme")
        channel = create_channel(
            db,
            tenant_id=tenant.id,
            channel_type="slack",
            name="Ops Slack",
            config_public={"channel": "#ops"},
            config_secret={"webhook_url": "https://hooks.slack.com/services/test"},
        )
        create_rule(
            db,
            tenant_id=tenant.id,
            name="Incident created",
            trigger_type="incident_created",
            route_to_channel_ids=[channel.id],
        )
        incident = _seed_incident(db, tenant.id)
        dispatch(
            db,
            event_type="incident_created",
            tenant_id=tenant.id,
            context_obj=incident,
        )

        called = {}

        def fake_post(url, json=None, timeout=10):
            called["url"] = url
            called["json"] = json

            class Resp:
                status_code = 200

            return Resp()

        monkeypatch.setattr(
            "app.notifications.senders.slack.requests.post",
            fake_post,
        )

        run_notification_sender(db, batch_size=10)
        delivery = db.query(NotificationDelivery).first()
        assert delivery.status == "sent"
        assert called["url"] == "https://hooks.slack.com/services/test"


def test_webhook_sender_signs_payload_correctly(monkeypatch):
    db_url = f"sqlite:///./notification_worker_webhook_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        tenant = create_tenant(db, name="Umbrella")
        channel = create_channel(
            db,
            tenant_id=tenant.id,
            channel_type="webhook",
            name="Security Webhook",
            config_public={"label": "security"},
            config_secret={"url": "https://example.com/hook", "signing_secret": "secret"},
        )
        create_rule(
            db,
            tenant_id=tenant.id,
            name="Incident created",
            trigger_type="incident_created",
            route_to_channel_ids=[channel.id],
        )
        incident = _seed_incident(db, tenant.id)
        dispatch(
            db,
            event_type="incident_created",
            tenant_id=tenant.id,
            context_obj=incident,
        )

        captured = {}

        def fake_post(url, data=None, headers=None, timeout=10):
            captured["url"] = url
            captured["data"] = data
            captured["headers"] = headers

            class Resp:
                status_code = 200

            return Resp()

        monkeypatch.setattr(
            "app.notifications.senders.webhook.requests.post",
            fake_post,
        )

        run_notification_sender(db, batch_size=10)
        assert captured["url"] == "https://example.com/hook"
        timestamp = captured["headers"].get("X-Timestamp")
        signature = captured["headers"].get("X-Signature")
        expected = _sign_payload("secret", timestamp, captured["data"])
        assert signature == expected


def test_notification_worker_retries_on_failure_and_marks_failed_after_max(monkeypatch):
    db_url = f"sqlite:///./notification_worker_retry_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        tenant = create_tenant(db, name="Wayne")
        channel = create_channel(
            db,
            tenant_id=tenant.id,
            channel_type="slack",
            name="Ops Slack",
            config_public={"channel": "#ops"},
            config_secret={"webhook_url": "https://hooks.slack.com/services/test"},
        )
        create_rule(
            db,
            tenant_id=tenant.id,
            name="Incident created",
            trigger_type="incident_created",
            route_to_channel_ids=[channel.id],
        )
        incident = _seed_incident(db, tenant.id)
        dispatch(
            db,
            event_type="incident_created",
            tenant_id=tenant.id,
            context_obj=incident,
        )

        def fail_send(*_args, **_kwargs):
            raise RuntimeError("send failed")

        monkeypatch.setattr(
            "app.notifications.senders.slack.SlackSender.send",
            fail_send,
        )

        run_notification_sender(db, batch_size=10, max_attempts=2, base_backoff_seconds=0)
        delivery = db.query(NotificationDelivery).first()
        assert delivery.status == "queued"
        assert delivery.attempt_count == 1

        run_notification_sender(db, batch_size=10, max_attempts=2, base_backoff_seconds=0)
        db.refresh(delivery)
        assert delivery.status == "failed"
        assert delivery.attempt_count == 2
