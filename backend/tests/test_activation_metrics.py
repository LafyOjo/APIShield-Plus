import os
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("SKIP_MIGRATIONS", "1")

import app.core.db as db_module
from app.crud.tenants import create_tenant
from app.crud.websites import create_website
from app.crud.website_environments import list_environments
from app.jobs.activation_metrics import run_activation_metrics_job
from app.models.activation_metrics import ActivationMetric
from app.models.behaviour_events import BehaviourEvent
from app.models.incidents import Incident
from app.models.prescriptions import PrescriptionBundle, PrescriptionItem


def _setup_db(db_url: str):
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        future=True,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db_module.engine = engine
    db_module.SessionLocal = SessionLocal
    db_module.Base.metadata.create_all(bind=engine)
    return SessionLocal


def _seed_event(db, *, tenant_id: int, website_id: int, env_id: int, event_ts: datetime):
    db.add(
        BehaviourEvent(
            tenant_id=tenant_id,
            website_id=website_id,
            environment_id=env_id,
            ingested_at=event_ts,
            event_ts=event_ts,
            event_id=f"evt-{event_ts.timestamp()}",
            event_type="page_view",
            url="https://example.com",
            path="/",
            referrer=None,
            session_id="s1",
            visitor_id=None,
            ip_hash=None,
            user_agent="ua",
            meta={},
        )
    )


def test_activation_metrics_time_to_first_event_recorded():
    db_url = f"sqlite:///./activation_time_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    with SessionLocal() as db:
        tenant = create_tenant(db, name="Tenant A")
        created_at = datetime.utcnow().replace(microsecond=0)
        tenant.created_at = created_at
        db.commit()

        website = create_website(db, tenant.id, "example.com")
        env = list_environments(db, website.id)[0]

        first_event = created_at + timedelta(hours=1)
        _seed_event(db, tenant_id=tenant.id, website_id=website.id, env_id=env.id, event_ts=first_event)
        db.commit()

        run_activation_metrics_job(db, tenant_id=tenant.id)
        metric = db.query(ActivationMetric).filter(ActivationMetric.tenant_id == tenant.id).first()
        assert metric is not None
        assert metric.time_to_first_event_seconds == 3600


def test_activation_score_updates_on_first_prescription_applied():
    db_url = f"sqlite:///./activation_score_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    with SessionLocal() as db:
        tenant = create_tenant(db, name="Tenant B")
        website = create_website(db, tenant.id, "example.com")
        env = list_environments(db, website.id)[0]

        now = datetime.utcnow()
        _seed_event(db, tenant_id=tenant.id, website_id=website.id, env_id=env.id, event_ts=now)
        db.commit()

        run_activation_metrics_job(db, tenant_id=tenant.id)
        metric = db.query(ActivationMetric).filter(ActivationMetric.tenant_id == tenant.id).first()
        assert metric is not None
        assert metric.activation_score == 30

        incident = Incident(
            tenant_id=tenant.id,
            website_id=website.id,
            environment_id=env.id,
            status="open",
            status_manual=True,
            category="login",
            title="Test incident",
            summary="Test",
            severity="high",
            first_seen_at=now,
            last_seen_at=now,
            evidence_json={},
        )
        db.add(incident)
        db.flush()

        bundle = PrescriptionBundle(
            tenant_id=tenant.id,
            website_id=website.id,
            environment_id=env.id,
            incident_id=incident.id,
            status="suggested",
            items_json=[],
        )
        db.add(bundle)
        db.flush()

        db.add(
            PrescriptionItem(
                bundle_id=bundle.id,
                tenant_id=tenant.id,
                website_id=website.id,
                environment_id=env.id,
                incident_id=incident.id,
                key="lockout",
                title="Lockout",
                priority="high",
                effort="low",
                expected_effect="reduce failures",
                status="applied",
                applied_at=now,
            )
        )
        db.commit()

        run_activation_metrics_job(db, tenant_id=tenant.id)
        metric = db.query(ActivationMetric).filter(ActivationMetric.tenant_id == tenant.id).first()
        assert metric is not None
        assert metric.activation_score == 50


def test_demo_mode_excluded_from_activation_metrics():
    db_url = f"sqlite:///./activation_demo_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    with SessionLocal() as db:
        tenant = create_tenant(db, name="Demo Tenant")
        tenant.is_demo_mode = True
        db.commit()

        website = create_website(db, tenant.id, "example.com")
        env = list_environments(db, website.id)[0]
        _seed_event(db, tenant_id=tenant.id, website_id=website.id, env_id=env.id, event_ts=datetime.utcnow())
        db.commit()

        updated = run_activation_metrics_job(db, tenant_id=tenant.id)
        assert updated == 0
        assert (
            db.query(ActivationMetric)
            .filter(ActivationMetric.tenant_id == tenant.id)
            .first()
            is None
        )
