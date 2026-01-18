import os
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("SKIP_MIGRATIONS", "1")

import app.models  # noqa: F401
from app.api.score import record_attempt
from app.core.db import Base
from app.core.events import log_event
from app.core.privacy import hash_ip
from app.crud.audit import create_audit_log
from app.models.alerts import Alert
from app.models.audit_logs import AuditLog
from app.models.events import Event
from tests.factories import make_tenant


def _setup_db(tmp_path):
    db_url = f"sqlite:///{tmp_path}/meta_{uuid4().hex}.db"
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        future=True,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    return SessionLocal


def test_event_logging_populates_ip_hash_user_agent_path(tmp_path):
    SessionLocal = _setup_db(tmp_path)
    with SessionLocal() as db:
        tenant = make_tenant(db, name="Acme")
        meta = {
            "client_ip": "203.0.113.10",
            "user_agent": "test-agent/1.0",
            "path": "/login",
            "referer": "https://example.com",
        }
        log_event(db, tenant.id, "alice", "login", True, request_meta=meta)
        event = db.query(Event).filter(Event.tenant_id == tenant.id).first()
        assert event is not None
        assert event.client_ip == "203.0.113.10"
        assert event.ip_hash == hash_ip(tenant.id, "203.0.113.10")
        assert event.user_agent == "test-agent/1.0"
        assert event.request_path == "/login"
        assert event.referrer == "https://example.com"


def test_alert_logging_populates_ip_hash_and_client_ip(tmp_path):
    SessionLocal = _setup_db(tmp_path)
    with SessionLocal() as db:
        tenant = make_tenant(db, name="Umbrella")
        meta = {
            "client_ip": "198.51.100.5",
            "user_agent": "agent/2.0",
            "path": "/score",
            "referer": "https://app.example.com",
        }
        record_attempt(
            db,
            "198.51.100.5",
            False,
            username="alice",
            tenant_id=tenant.id,
            request_meta=meta,
        )
        alert = db.query(Alert).filter(Alert.tenant_id == tenant.id).first()
        assert alert is not None
        assert alert.client_ip == "198.51.100.5"
        assert alert.ip_hash == hash_ip(tenant.id, "198.51.100.5")
        assert alert.user_agent == "agent/2.0"
        assert alert.request_path == "/score"
        assert alert.referrer == "https://app.example.com"


def test_audit_logging_populates_ip_fields(tmp_path):
    SessionLocal = _setup_db(tmp_path)
    with SessionLocal() as db:
        tenant = make_tenant(db, name="Wayne")
        meta = {
            "client_ip": "192.0.2.9",
            "user_agent": "audit-agent/3.0",
            "path": "/api/v1/invites",
            "referer": "https://console.example.com",
        }
        log_row = create_audit_log(
            db,
            tenant_id=tenant.id,
            username="bruce",
            event="user_login_success",
            request_meta=meta,
        )
        assert isinstance(log_row, AuditLog)
        assert log_row.client_ip == "192.0.2.9"
        assert log_row.ip_hash == hash_ip(tenant.id, "192.0.2.9")
        assert log_row.user_agent == "audit-agent/3.0"
        assert log_row.request_path == "/api/v1/invites"
        assert log_row.referrer == "https://console.example.com"


def test_ip_hash_not_same_across_tenants_for_same_ip(tmp_path):
    SessionLocal = _setup_db(tmp_path)
    with SessionLocal() as db:
        tenant_a = make_tenant(db, name="Stark")
        tenant_b = make_tenant(db, name="Stark Two")
        ip_value = "203.0.113.10"
        assert hash_ip(tenant_a.id, ip_value) != hash_ip(tenant_b.id, ip_value)
