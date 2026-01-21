import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("SKIP_MIGRATIONS", "1")

import app.core.db as db_module
from app.core.privacy import hash_ip
from app.core.time import utcnow
from app.core.incidents import create_incident_from_signal
from app.crud.tenants import create_tenant
from app.crud.websites import create_website
from app.crud.website_environments import list_environments
from app.models.incidents import Incident, IncidentSecurityEventLink
from app.models.security_events import SecurityEvent
from app.security.taxonomy import SecurityEventTypeEnum, get_category, get_severity


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


def _seed_security_event(
    db,
    *,
    tenant_id: int,
    website_id: int,
    env_id: int,
    ip_hash: str,
    event_ts: datetime,
    event_type: SecurityEventTypeEnum = SecurityEventTypeEnum.LOGIN_ATTEMPT_FAILED,
):
    db.add(
        SecurityEvent(
            tenant_id=tenant_id,
            website_id=website_id,
            environment_id=env_id,
            event_ts=event_ts,
            event_type=event_type.value,
            category=get_category(event_type).value,
            severity=get_severity(event_type).value,
            source="server",
            request_path="/login",
            ip_hash=ip_hash,
        )
    )


def test_incident_created_and_links_security_events():
    db_url = f"sqlite:///./incidents_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    with SessionLocal() as db:
        tenant = create_tenant(db, name="Tenant A")
        website = create_website(db, tenant.id, "example.com")
        env = list_environments(db, website.id)[0]
        ip_hash = hash_ip(tenant.id, "203.0.113.30")
        _seed_security_event(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            env_id=env.id,
            ip_hash=ip_hash,
            event_ts=utcnow(),
        )
        db.commit()

        event = db.query(SecurityEvent).first()
        incident = create_incident_from_signal(db, signal=event)
        db.commit()

        assert incident is not None
        assert incident.tenant_id == tenant.id
        assert incident.category == "login"
        link_count = db.query(IncidentSecurityEventLink).count()
        assert link_count == 1


def test_incident_clustering_attaches_to_existing_incident_window():
    db_url = f"sqlite:///./incidents_cluster_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    with SessionLocal() as db:
        tenant = create_tenant(db, name="Tenant A")
        website = create_website(db, tenant.id, "example.com")
        env = list_environments(db, website.id)[0]
        ip_hash = hash_ip(tenant.id, "203.0.113.31")
        now = datetime.now(timezone.utc)
        _seed_security_event(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            env_id=env.id,
            ip_hash=ip_hash,
            event_ts=now - timedelta(minutes=5),
        )
        _seed_security_event(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            env_id=env.id,
            ip_hash=ip_hash,
            event_ts=now - timedelta(minutes=10),
            event_type=SecurityEventTypeEnum.LOGIN_ATTEMPT,
        )
        db.commit()

        events = db.query(SecurityEvent).order_by(SecurityEvent.event_ts.asc()).all()
        first_incident = create_incident_from_signal(db, signal=events[0])
        second_incident = create_incident_from_signal(db, signal=events[1])
        db.commit()

        assert first_incident.id == second_incident.id
        assert db.query(Incident).count() == 1
        assert db.query(IncidentSecurityEventLink).count() == 2


def test_incident_tenant_scoping_enforced():
    db_url = f"sqlite:///./incidents_scope_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    with SessionLocal() as db:
        tenant_a = create_tenant(db, name="Tenant A")
        tenant_b = create_tenant(db, name="Tenant B")
        website_a = create_website(db, tenant_a.id, "a.example.com")
        website_b = create_website(db, tenant_b.id, "b.example.com")
        env_a = list_environments(db, website_a.id)[0]
        env_b = list_environments(db, website_b.id)[0]
        ip_hash_a = hash_ip(tenant_a.id, "203.0.113.40")
        ip_hash_b = hash_ip(tenant_b.id, "203.0.113.41")
        _seed_security_event(
            db,
            tenant_id=tenant_a.id,
            website_id=website_a.id,
            env_id=env_a.id,
            ip_hash=ip_hash_a,
            event_ts=utcnow(),
        )
        _seed_security_event(
            db,
            tenant_id=tenant_b.id,
            website_id=website_b.id,
            env_id=env_b.id,
            ip_hash=ip_hash_b,
            event_ts=utcnow(),
        )
        db.commit()

        events = db.query(SecurityEvent).order_by(SecurityEvent.tenant_id.asc()).all()
        incident_a = create_incident_from_signal(db, signal=events[0])
        incident_b = create_incident_from_signal(db, signal=events[1])
        db.commit()

        assert incident_a.tenant_id == tenant_a.id
        assert incident_b.tenant_id == tenant_b.id
        assert db.query(Incident).count() == 2
