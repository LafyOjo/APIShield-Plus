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
from app.insights.incident_status import evaluate_status_transition
from app.insights.interpretation import interpret_incident
from app.insights.recovery import compute_recovery
from app.models.behaviour_events import BehaviourEvent
from app.models.incidents import Incident
from app.models.prescriptions import PrescriptionBundle, PrescriptionItem
from app.models.security_events import SecurityEvent


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
        db.add(
            BehaviourEvent(
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
        )
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


def _seed_security_events(
    db,
    *,
    tenant_id: int,
    website_id: int,
    env_id: int,
    base_ts: datetime,
    count: int,
    category: str,
    prefix: str,
):
    for idx in range(count):
        db.add(
            SecurityEvent(
                tenant_id=tenant_id,
                website_id=website_id,
                environment_id=env_id,
                event_ts=base_ts + timedelta(minutes=idx),
                created_at=base_ts + timedelta(minutes=idx),
                category=category,
                event_type=f"{prefix}_event",
                severity="high",
                source="server",
            )
        )


def _seed_prescriptions(
    db,
    *,
    tenant_id: int,
    website_id: int,
    env_id: int,
    incident_id: int,
    applied_at: datetime,
):
    bundle = PrescriptionBundle(
        tenant_id=tenant_id,
        website_id=website_id,
        environment_id=env_id,
        incident_id=incident_id,
        status="suggested",
        items_json=[],
    )
    db.add(bundle)
    db.flush()
    db.add(
        PrescriptionItem(
            bundle_id=bundle.id,
            tenant_id=tenant_id,
            website_id=website_id,
            environment_id=env_id,
            incident_id=incident_id,
            key="login_hardening",
            title="Harden login protections",
            priority="P1",
            effort="med",
            expected_effect="security",
            status="applied",
            applied_at=applied_at,
        )
    )


def _seed_incident(
    db,
    *,
    tenant_id: int,
    website_id: int,
    env_id: int,
    start: datetime,
    end: datetime,
    category: str,
    status: str,
    severity: str = "medium",
):
    incident = Incident(
        tenant_id=tenant_id,
        website_id=website_id,
        environment_id=env_id,
        status=status,
        category=category,
        title="Checkout anomaly",
        summary=None,
        severity=severity,
        first_seen_at=start,
        last_seen_at=end,
        primary_ip_hash=None,
        primary_country_code=None,
        evidence_json={"request_paths": {"/checkout": 6}, "counts": {"security_events": 6}},
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident


def test_incident_status_open_to_investigating_on_high_impact():
    db_url = f"sqlite:///./incident_status_open_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    with SessionLocal() as db:
        tenant = create_tenant(db, name="Tenant A")
        website = create_website(db, tenant.id, "example.com")
        env = list_environments(db, website.id)[0]
        now = datetime.utcnow()
        incident_start = now - timedelta(days=2)
        incident_end = incident_start + timedelta(hours=1)
        baseline_ts = incident_start - timedelta(days=7)

        _seed_events(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            env_id=env.id,
            path="/checkout",
            base_ts=baseline_ts,
            sessions=80,
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

        incident = _seed_incident(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            env_id=env.id,
            start=incident_start,
            end=incident_end,
            category="integrity",
            status="open",
            severity="medium",
        )

        impact = interpret_incident(db, incident.id)
        db.commit()
        assert impact is not None

        next_status = evaluate_status_transition(db, incident, impact=impact)
        assert next_status == "investigating"


def test_incident_status_investigating_to_mitigated_on_recovery():
    db_url = f"sqlite:///./incident_status_mitigated_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    with SessionLocal() as db:
        tenant = create_tenant(db, name="Tenant A")
        website = create_website(db, tenant.id, "example.com")
        env = list_environments(db, website.id)[0]
        now = datetime.utcnow()
        incident_start = now - timedelta(days=2)
        incident_end = incident_start + timedelta(hours=1)
        baseline_ts = incident_start - timedelta(days=7)
        post_start = now - timedelta(days=1)

        _seed_events(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            env_id=env.id,
            path="/checkout",
            base_ts=baseline_ts,
            sessions=80,
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
        _seed_events(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            env_id=env.id,
            path="/checkout",
            base_ts=post_start,
            sessions=40,
            submit_ratio=0.45,
            error_ratio=0.05,
            prefix="post",
        )

        incident = _seed_incident(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            env_id=env.id,
            start=incident_start,
            end=incident_end,
            category="threat",
            status="investigating",
        )
        _seed_prescriptions(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            env_id=env.id,
            incident_id=incident.id,
            applied_at=post_start,
        )
        _seed_security_events(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            env_id=env.id,
            base_ts=incident_start,
            count=6,
            category="threat",
            prefix="incident",
        )
        _seed_security_events(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            env_id=env.id,
            base_ts=post_start,
            count=2,
            category="threat",
            prefix="post",
        )
        db.commit()

        impact = interpret_incident(db, incident.id)
        db.commit()
        assert impact is not None

        recovery_result = compute_recovery(db, incident.id, window_hours=6)
        db.commit()
        assert recovery_result is not None

        next_status = evaluate_status_transition(
            db,
            incident,
            impact=impact,
            recovery=recovery_result["recovery"],
        )
        assert next_status == "mitigated"


def test_incident_status_mitigated_to_resolved_after_cooldown_and_stability():
    db_url = f"sqlite:///./incident_status_resolved_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    with SessionLocal() as db:
        tenant = create_tenant(db, name="Tenant A")
        website = create_website(db, tenant.id, "example.com")
        env = list_environments(db, website.id)[0]
        now = datetime.utcnow()
        incident_start = now - timedelta(days=2)
        incident_end = incident_start + timedelta(hours=1)
        baseline_ts = incident_start - timedelta(days=7)
        post_start = now - timedelta(hours=12)

        _seed_events(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            env_id=env.id,
            path="/checkout",
            base_ts=baseline_ts,
            sessions=80,
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
        _seed_events(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            env_id=env.id,
            path="/checkout",
            base_ts=post_start,
            sessions=40,
            submit_ratio=0.5,
            error_ratio=0.0,
            prefix="post",
        )

        incident = _seed_incident(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            env_id=env.id,
            start=incident_start,
            end=incident_end,
            category="threat",
            status="mitigated",
        )
        _seed_prescriptions(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            env_id=env.id,
            incident_id=incident.id,
            applied_at=post_start,
        )
        _seed_security_events(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            env_id=env.id,
            base_ts=incident_start,
            count=6,
            category="threat",
            prefix="incident",
        )
        db.commit()

        impact = interpret_incident(db, incident.id)
        db.commit()
        assert impact is not None

        recovery_result = compute_recovery(db, incident.id, window_hours=6)
        db.commit()
        assert recovery_result is not None

        next_status = evaluate_status_transition(
            db,
            incident,
            impact=impact,
            recovery=recovery_result["recovery"],
            now=now,
        )
        assert next_status == "resolved"
