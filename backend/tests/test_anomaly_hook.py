import os
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("ZERO_TRUST_API_KEY", "")
os.environ.setdefault("SKIP_MIGRATIONS", "1")

from app.main import app
import app.core.db as db_module
import app.core.access_log as access_log_module
import app.core.policy as policy_module
from app.core.rate_limit import reset_state
from app.core.security import get_password_hash
from app.crud.api_keys import create_api_key
from app.crud.memberships import create_membership
from app.crud.tenants import create_tenant
from app.crud.users import create_user
from app.crud.website_environments import list_environments
from app.crud.websites import create_website
from app.models.anomaly_signals import AnomalySignalEvent
from app.models.enums import RoleEnum
from app.models.users import User


client = TestClient(app)


def _setup_db(db_url: str):
    reset_state()
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        future=True,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db_module.engine = engine
    db_module.SessionLocal = SessionLocal
    access_log_module.SessionLocal = SessionLocal
    policy_module.SessionLocal = SessionLocal
    access_log_module.create_access_log = lambda db, username, path: None
    db_module.Base.metadata.create_all(bind=engine)
    return SessionLocal


def _setup_ingest(SessionLocal, *, username: str, tenant_name: str, domain: str):
    with SessionLocal() as db:
        owner = create_user(db, username=username, password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name=tenant_name)
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=owner.id,
            role=RoleEnum.OWNER,
            created_by_user_id=owner.id,
        )
        website = create_website(db, tenant.id, domain, created_by_user_id=owner.id)
        environment = list_environments(db, website.id)[0]
        api_key, _raw_secret = create_api_key(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            environment_id=environment.id,
            name="Anomaly Key",
            created_by_user_id=owner.id,
        )
        db.commit()
        return tenant.id, api_key.public_key


def test_ingest_creates_anomaly_signal_on_error_event():
    db_url = f"sqlite:///./anomaly_error_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_id, api_key = _setup_ingest(
        SessionLocal,
        username="anomaly-owner",
        tenant_name="AnomalyTenant",
        domain="example.com",
    )

    event_id = str(uuid4())
    payload = {
        "event_id": event_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": "error",
        "url": "https://example.com/checkout",
        "path": "/checkout",
        "session_id": "s_err",
        "meta": {"message": "fail"},
    }
    resp = client.post(
        "/api/v1/ingest/browser",
        json=payload,
        headers={"X-Api-Key": api_key},
    )
    assert resp.status_code == 200

    with SessionLocal() as db:
        signal = (
            db.query(AnomalySignalEvent)
            .filter(AnomalySignalEvent.tenant_id == tenant_id)
            .first()
        )
        assert signal is not None
        assert signal.signal_type == "js_error_event"
        assert signal.event_id == event_id


def test_anomaly_signal_tenant_scoped():
    db_url = f"sqlite:///./anomaly_scope_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_a_id, api_key_a = _setup_ingest(
        SessionLocal,
        username="anomaly-owner",
        tenant_name="AnomalyTenantA",
        domain="a.example.com",
    )
    with SessionLocal() as db:
        owner = db.query(User).filter(User.username == "anomaly-owner").first()
        tenant_b = create_tenant(db, name="AnomalyTenantB")
        create_membership(
            db,
            tenant_id=tenant_b.id,
            user_id=owner.id,
            role=RoleEnum.OWNER,
            created_by_user_id=owner.id,
        )
        website_b = create_website(db, tenant_b.id, "b.example.com", created_by_user_id=owner.id)
        environment_b = list_environments(db, website_b.id)[0]
        api_key_b, _raw_secret = create_api_key(
            db,
            tenant_id=tenant_b.id,
            website_id=website_b.id,
            environment_id=environment_b.id,
            name="Anomaly Key",
            created_by_user_id=owner.id,
        )
        api_key_b = api_key_b.public_key
        tenant_b_id = tenant_b.id

    payload_a = {
        "event_id": str(uuid4()),
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": "error",
        "url": "https://a.example.com/",
        "path": "/",
        "session_id": "s_a",
    }
    payload_b = {
        "event_id": str(uuid4()),
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": "error",
        "url": "https://b.example.com/",
        "path": "/",
        "session_id": "s_b",
    }
    resp = client.post("/api/v1/ingest/browser", json=payload_a, headers={"X-Api-Key": api_key_a})
    assert resp.status_code == 200
    resp = client.post("/api/v1/ingest/browser", json=payload_b, headers={"X-Api-Key": api_key_b})
    assert resp.status_code == 200

    with SessionLocal() as db:
        count_a = (
            db.query(AnomalySignalEvent)
            .filter(AnomalySignalEvent.tenant_id == tenant_a_id)
            .count()
        )
        count_b = (
            db.query(AnomalySignalEvent)
            .filter(AnomalySignalEvent.tenant_id == tenant_b_id)
            .count()
        )
        assert count_a == 1
        assert count_b == 1


def test_anomaly_hook_failure_does_not_break_ingest(monkeypatch):
    db_url = f"sqlite:///./anomaly_fail_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    _tenant_id, api_key = _setup_ingest(
        SessionLocal,
        username="anomaly-fail",
        tenant_name="AnomalyFailTenant",
        domain="example.com",
    )

    import app.api.ingest as ingest_module

    def _raise(_ctx, _event):
        raise RuntimeError("boom")

    monkeypatch.setattr(ingest_module, "evaluate_event_for_anomaly", _raise)

    payload = {
        "event_id": str(uuid4()),
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": "page_view",
        "url": "https://example.com/",
        "path": "/",
        "session_id": "s_safe",
    }
    resp = client.post(
        "/api/v1/ingest/browser",
        json=payload,
        headers={"X-Api-Key": api_key},
    )
    assert resp.status_code == 200
