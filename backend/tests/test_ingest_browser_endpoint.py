import os
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("ZERO_TRUST_API_KEY", "")
os.environ["SKIP_MIGRATIONS"] = "1"

from app.main import app
import app.core.db as db_module
import app.core.access_log as access_log_module
import app.core.policy as policy_module
from app.core.db import Base
from app.core.security import get_password_hash
from app.core.rate_limit import reset_state
from app.crud.api_keys import create_api_key
from app.crud.memberships import create_membership
from app.crud.tenants import create_tenant
from app.crud.users import create_user
from app.crud.website_environments import list_environments
from app.crud.websites import create_website
from app.models.api_keys import APIKey
from app.models.behaviour_events import BehaviourEvent
from app.models.enums import RoleEnum, WebsiteStatusEnum
from app.models.websites import Website


client = TestClient(app)


def _setup_db(db_url: str):
    reset_state()
    from app.models.behaviour_sessions import BehaviourSession

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
    Base.metadata.create_all(bind=engine)
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
            name="Browser Key",
            created_by_user_id=owner.id,
        )
        db.commit()
        return tenant.id, website.id, environment.id, api_key.public_key


def test_ingest_browser_valid_key_stores_event():
    db_url = f"sqlite:///./ingest_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_id, website_id, environment_id, api_key = _setup_ingest(
        SessionLocal,
        username="ingest-user",
        tenant_name="IngestTenant",
        domain="example.com",
    )

    payload = {
        "event_id": str(uuid4()),
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": "page_view",
        "url": "https://example.com/pricing",
        "path": "/pricing",
        "referrer": "https://google.com",
        "session_id": "s_abc123",
        "user_id": None,
        "meta": {"viewport": "1440x900", "lang": "en-GB"},
    }
    resp = client.post(
        "/api/v1/ingest/browser",
        json=payload,
        headers={"X-Api-Key": api_key, "X-Forwarded-For": "203.0.113.9"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True

    with SessionLocal() as db:
        stored = db.query(BehaviourEvent).first()
        assert stored is not None
        assert stored.tenant_id == tenant_id
        assert stored.website_id == website_id
        assert stored.environment_id == environment_id


def test_ingest_browser_revoked_key_rejected():
    db_url = f"sqlite:///./ingest_revoked_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    _tenant_id, _website_id, _environment_id, api_key = _setup_ingest(
        SessionLocal,
        username="ingest-revoke",
        tenant_name="IngestRevoke",
        domain="example.com",
    )
    with SessionLocal() as db:
        key = db.query(APIKey).filter_by(public_key=api_key).first()
        key.revoked_at = datetime.now(timezone.utc)
        key.status = "revoked"
        db.commit()

    payload = {
        "event_id": str(uuid4()),
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": "page_view",
        "url": "https://example.com/",
        "path": "/",
    }
    resp = client.post(
        "/api/v1/ingest/browser",
        json=payload,
        headers={"X-Api-Key": api_key},
    )
    assert resp.status_code == 401


def test_ingest_browser_domain_mismatch_rejected():
    db_url = f"sqlite:///./ingest_domain_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    _tenant_id, _website_id, _environment_id, api_key = _setup_ingest(
        SessionLocal,
        username="ingest-domain",
        tenant_name="IngestDomain",
        domain="example.com",
    )

    payload = {
        "event_id": str(uuid4()),
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": "page_view",
        "url": "https://evil.com/",
        "path": "/",
    }
    resp = client.post(
        "/api/v1/ingest/browser",
        json=payload,
        headers={"X-Api-Key": api_key},
    )
    assert resp.status_code == 400


def test_ingest_browser_populates_ip_hash_and_user_agent():
    db_url = f"sqlite:///./ingest_ip_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_id, website_id, environment_id, api_key = _setup_ingest(
        SessionLocal,
        username="ingest-ip",
        tenant_name="IngestIpTenant",
        domain="example.com",
    )

    payload = {
        "event_id": str(uuid4()),
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": "page_view",
        "url": "https://example.com/",
        "path": "/",
    }
    resp = client.post(
        "/api/v1/ingest/browser",
        json=payload,
        headers={
            "X-Api-Key": api_key,
            "X-Forwarded-For": "198.51.100.10",
            "User-Agent": "agent-test/1.0",
        },
    )
    assert resp.status_code == 200

    with SessionLocal() as db:
        stored = db.query(BehaviourEvent).filter_by(tenant_id=tenant_id).first()
        assert stored is not None
        assert stored.ip_hash is not None
        assert stored.user_agent == "agent-test/1.0"
        assert stored.website_id == website_id
        assert stored.environment_id == environment_id


def test_ingest_browser_rejects_inactive_website():
    db_url = f"sqlite:///./ingest_inactive_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_id, website_id, _environment_id, api_key = _setup_ingest(
        SessionLocal,
        username="ingest-inactive",
        tenant_name="IngestInactive",
        domain="example.com",
    )
    with SessionLocal() as db:
        site = db.query(Website).filter_by(id=website_id).first()
        site.status = WebsiteStatusEnum.PAUSED
        db.commit()

    payload = {
        "event_id": str(uuid4()),
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": "page_view",
        "url": "https://example.com/",
        "path": "/",
    }
    resp = client.post(
        "/api/v1/ingest/browser",
        json=payload,
        headers={"X-Api-Key": api_key},
    )
    assert resp.status_code == 404


def test_ingest_rejects_unknown_event_type():
    db_url = f"sqlite:///./ingest_type_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    _tenant_id, _website_id, _environment_id, api_key = _setup_ingest(
        SessionLocal,
        username="ingest-type",
        tenant_name="IngestTypeTenant",
        domain="example.com",
    )

    payload = {
        "event_id": str(uuid4()),
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": "unknown_event",
        "url": "https://example.com/",
        "path": "/",
    }
    resp = client.post(
        "/api/v1/ingest/browser",
        json=payload,
        headers={"X-Api-Key": api_key},
    )
    assert resp.status_code == 422


def test_ingest_dedupes_same_event_id():
    db_url = f"sqlite:///./ingest_dedupe_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_id, _website_id, _environment_id, api_key = _setup_ingest(
        SessionLocal,
        username="ingest-dedupe",
        tenant_name="IngestDedupeTenant",
        domain="example.com",
    )

    event_id = str(uuid4())
    payload = {
        "event_id": event_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": "page_view",
        "url": "https://example.com/",
        "path": "/",
    }
    resp_first = client.post(
        "/api/v1/ingest/browser",
        json=payload,
        headers={"X-Api-Key": api_key},
    )
    assert resp_first.status_code == 200
    assert resp_first.json().get("deduped") is False

    resp_second = client.post(
        "/api/v1/ingest/browser",
        json=payload,
        headers={"X-Api-Key": api_key},
    )
    assert resp_second.status_code == 200
    assert resp_second.json().get("deduped") is True

    with SessionLocal() as db:
        count = db.query(BehaviourEvent).filter_by(tenant_id=tenant_id).count()
        assert count == 1


def test_ingest_normalizes_url_and_path():
    db_url = f"sqlite:///./ingest_normalize_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_id, _website_id, _environment_id, api_key = _setup_ingest(
        SessionLocal,
        username="ingest-normalize",
        tenant_name="IngestNormalizeTenant",
        domain="example.com",
    )

    payload = {
        "event_id": str(uuid4()),
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": "page_view",
        "url": "https://Example.com/Shop?utm=1#section",
        "path": "/Shop?utm=1#section",
    }
    resp = client.post(
        "/api/v1/ingest/browser",
        json=payload,
        headers={"X-Api-Key": api_key},
    )
    assert resp.status_code == 200

    with SessionLocal() as db:
        stored = db.query(BehaviourEvent).filter_by(tenant_id=tenant_id).first()
        assert stored is not None
        assert stored.url == "https://example.com/Shop"
        assert stored.path == "/Shop"
