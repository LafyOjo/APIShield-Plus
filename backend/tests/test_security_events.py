import os
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("SKIP_MIGRATIONS", "1")

from app.core.db import Base
from app.crud.tenants import create_tenant
from app.models.security_events import SecurityEvent


def _setup_db(db_url: str):
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        future=True,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    return SessionLocal


def test_security_event_insert_and_query_scoped(tmp_path):
    db_url = f"sqlite:///{tmp_path}/security_events_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    with SessionLocal() as db:
        tenant_a = create_tenant(db, name="Tenant A")
        tenant_b = create_tenant(db, name="Tenant B")
        db.add(
            SecurityEvent(
                tenant_id=tenant_a.id,
                category="login",
                event_type="login_attempt",
                severity="low",
                source="server",
                event_ts=datetime.utcnow(),
                ip_hash="hash-a",
            )
        )
        db.add(
            SecurityEvent(
                tenant_id=tenant_b.id,
                category="threat",
                event_type="credential_stuffing",
                severity="high",
                source="waf",
                event_ts=datetime.utcnow(),
                ip_hash="hash-b",
            )
        )
        db.commit()

        events_a = (
            db.query(SecurityEvent)
            .filter(SecurityEvent.tenant_id == tenant_a.id)
            .all()
        )
        events_b = (
            db.query(SecurityEvent)
            .filter(SecurityEvent.tenant_id == tenant_b.id)
            .all()
        )

        assert len(events_a) == 1
        assert len(events_b) == 1
        assert events_a[0].tenant_id == tenant_a.id
        assert events_b[0].tenant_id == tenant_b.id


def test_security_event_requires_category_and_severity(tmp_path):
    db_url = f"sqlite:///{tmp_path}/security_events_required_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    with SessionLocal() as db:
        tenant = create_tenant(db, name="Tenant C")

        db.add(
            SecurityEvent(
                tenant_id=tenant.id,
                category=None,
                event_type="login_attempt",
                severity="low",
                source="server",
                event_ts=datetime.utcnow(),
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        db.add(
            SecurityEvent(
                tenant_id=tenant.id,
                category="login",
                event_type="login_attempt",
                severity=None,
                source="server",
                event_ts=datetime.utcnow(),
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
