import os
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("SKIP_MIGRATIONS", "1")

import app.core.db as db_module
from app.crud.tenants import create_tenant
from app.crud.websites import create_website
from app.crud.website_environments import list_environments
from app.insights.interpretation import interpret_incident
from app.models.behaviour_events import BehaviourEvent
from app.models.incidents import Incident


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


def _seed_events(
    db,
    *,
    tenant_id: int,
    website_id: int,
    env_id: int,
    path: str,
    base_ts: datetime,
    sessions: int,
    submit_ratio: float,
    error_ratio: float,
    prefix: str,
):
    submit_count = int(sessions * submit_ratio)
    error_count = int(sessions * error_ratio)
    for idx in range(sessions):
        session_id = f"{prefix}_{idx}"
        view_event = BehaviourEvent(
            tenant_id=tenant_id,
            website_id=website_id,
            environment_id=env_id,
            event_ts=base_ts + timedelta(seconds=idx),
            event_id=uuid4().hex,
            event_type="page_view",
            url=f"https://example.com{path}",
            path=path,
            session_id=session_id,
        )
        db.add(view_event)
        if idx < submit_count:
            db.add(
                BehaviourEvent(
                    tenant_id=tenant_id,
                    website_id=website_id,
                    environment_id=env_id,
                    event_ts=base_ts + timedelta(seconds=idx, milliseconds=10),
                    event_id=uuid4().hex,
                    event_type="form_submit",
                    url=f"https://example.com{path}",
                    path=path,
                    session_id=session_id,
                )
            )
        if idx < error_count:
            db.add(
                BehaviourEvent(
                    tenant_id=tenant_id,
                    website_id=website_id,
                    environment_id=env_id,
                    event_ts=base_ts + timedelta(seconds=idx, milliseconds=20),
                    event_id=uuid4().hex,
                    event_type="error",
                    url=f"https://example.com{path}",
                    path=path,
                    session_id=session_id,
                )
            )


def test_interpret_incident_generates_impact_estimate():
    db_url = f"sqlite:///./interpret_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    with SessionLocal() as db:
        tenant = create_tenant(db, name="Tenant A")
        website = create_website(db, tenant.id, "example.com")
        env = list_environments(db, website.id)[0]

        incident_start = datetime(2026, 1, 10, 10, 0, 0)
        incident_end = incident_start + timedelta(hours=1)
        baseline_ts = incident_start - timedelta(days=7)

        _seed_events(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            env_id=env.id,
            path="/checkout",
            base_ts=baseline_ts,
            sessions=60,
            submit_ratio=0.5,
            error_ratio=0.0,
            prefix="baseline",
        )
        _seed_events(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            env_id=env.id,
            path="/checkout",
            base_ts=incident_start,
            sessions=40,
            submit_ratio=0.1,
            error_ratio=0.2,
            prefix="incident",
        )

        incident = Incident(
            tenant_id=tenant.id,
            website_id=website.id,
            environment_id=env.id,
            status="open",
            category="integrity",
            title="Checkout anomaly",
            summary=None,
            severity="high",
            first_seen_at=incident_start,
            last_seen_at=incident_end,
            primary_ip_hash=None,
            primary_country_code=None,
            evidence_json={"request_paths": {"/checkout": 6}, "counts": {"security_events": 6}},
        )
        db.add(incident)
        db.commit()

        impact = interpret_incident(db, incident.id)
        db.commit()

        assert impact is not None
        assert impact.metric_key == "checkout_conversion"
        assert impact.estimated_lost_conversions > 0
        assert impact.confidence > 0


def test_interpretation_confidence_increases_with_path_overlap_and_spikes():
    db_url = f"sqlite:///./interpret_conf_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    with SessionLocal() as db:
        tenant = create_tenant(db, name="Tenant A")
        website = create_website(db, tenant.id, "example.com")
        env = list_environments(db, website.id)[0]

        incident_start = datetime(2026, 1, 12, 9, 0, 0)
        incident_end = incident_start + timedelta(hours=1)
        baseline_ts = incident_start - timedelta(days=7)

        _seed_events(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            env_id=env.id,
            path="/checkout",
            base_ts=baseline_ts,
            sessions=60,
            submit_ratio=0.5,
            error_ratio=0.0,
            prefix="baseline_checkout",
        )
        _seed_events(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            env_id=env.id,
            path="/checkout",
            base_ts=incident_start,
            sessions=40,
            submit_ratio=0.1,
            error_ratio=0.4,
            prefix="incident_checkout",
        )

        _seed_events(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            env_id=env.id,
            path="/profile",
            base_ts=baseline_ts,
            sessions=60,
            submit_ratio=0.5,
            error_ratio=0.0,
            prefix="baseline_profile",
        )
        _seed_events(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            env_id=env.id,
            path="/profile",
            base_ts=incident_start,
            sessions=40,
            submit_ratio=0.1,
            error_ratio=0.0,
            prefix="incident_profile",
        )

        checkout_incident = Incident(
            tenant_id=tenant.id,
            website_id=website.id,
            environment_id=env.id,
            status="open",
            category="integrity",
            title="Checkout spike",
            summary=None,
            severity="high",
            first_seen_at=incident_start,
            last_seen_at=incident_end,
            primary_ip_hash=None,
            primary_country_code=None,
            evidence_json={"request_paths": {"/checkout": 8}, "counts": {"security_events": 8}},
        )
        profile_incident = Incident(
            tenant_id=tenant.id,
            website_id=website.id,
            environment_id=env.id,
            status="open",
            category="integrity",
            title="Profile drop",
            summary=None,
            severity="high",
            first_seen_at=incident_start,
            last_seen_at=incident_end,
            primary_ip_hash=None,
            primary_country_code=None,
            evidence_json={"request_paths": {"/profile": 8}, "counts": {"security_events": 8}},
        )
        db.add(checkout_incident)
        db.add(profile_incident)
        db.commit()

        impact_checkout = interpret_incident(db, checkout_incident.id)
        impact_profile = interpret_incident(db, profile_incident.id)
        db.commit()

        assert impact_checkout is not None
        assert impact_profile is not None
        assert impact_checkout.confidence > impact_profile.confidence


def test_interpretation_does_not_generate_when_insufficient_data():
    db_url = f"sqlite:///./interpret_empty_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    with SessionLocal() as db:
        tenant = create_tenant(db, name="Tenant A")
        website = create_website(db, tenant.id, "example.com")
        env = list_environments(db, website.id)[0]

        incident_start = datetime(2026, 1, 15, 11, 0, 0)
        incident_end = incident_start + timedelta(hours=1)

        incident = Incident(
            tenant_id=tenant.id,
            website_id=website.id,
            environment_id=env.id,
            status="open",
            category="integrity",
            title="No data",
            summary=None,
            severity="medium",
            first_seen_at=incident_start,
            last_seen_at=incident_end,
            primary_ip_hash=None,
            primary_country_code=None,
            evidence_json={"request_paths": {"/checkout": 2}, "counts": {"security_events": 2}},
        )
        db.add(incident)
        db.commit()

        impact = interpret_incident(db, incident.id)
        db.commit()

        assert impact is None
