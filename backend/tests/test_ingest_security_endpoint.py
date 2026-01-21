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
from app.core.rate_limit import reset_state
from app.core.security import get_password_hash
from app.crud.api_keys import create_api_key
from app.crud.memberships import create_membership
from app.crud.tenants import create_tenant
from app.crud.users import create_user
from app.crud.website_environments import list_environments
from app.crud.websites import create_website
from app.models.api_keys import APIKey
from app.models.enums import RoleEnum
from app.models.security_events import SecurityEvent


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
        api_key, raw_secret = create_api_key(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            environment_id=environment.id,
            name="Server Key",
            created_by_user_id=owner.id,
        )
        db.commit()
        return tenant.id, api_key.public_key, raw_secret


def test_ingest_security_requires_secret_key():
    db_url = f"sqlite:///./ingest_security_{uuid4().hex}.db"
    _setup_db(db_url)

    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event_type": "login_attempt_failed",
        "severity": "medium",
        "request_path": "/login",
    }
    resp = client.post("/api/v1/ingest/security", json=payload)
    assert resp.status_code == 401


def test_ingest_security_maps_event_type_to_category():
    db_url = f"sqlite:///./ingest_security_map_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_id, _public_key, raw_secret = _setup_ingest(
        SessionLocal,
        username="security-map",
        tenant_name="SecurityMap",
        domain="example.com",
    )

    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event_type": "sql_injection_attempt",
        "severity": "high",
        "request_path": "/search",
    }
    resp = client.post(
        "/api/v1/ingest/security",
        json=payload,
        headers={"X-Api-Secret": raw_secret},
    )
    assert resp.status_code == 200

    with SessionLocal() as db:
        stored = db.query(SecurityEvent).filter_by(tenant_id=tenant_id).first()
        assert stored is not None
        assert stored.category == "threat"


def test_ingest_security_populates_ip_hash_and_user_agent():
    db_url = f"sqlite:///./ingest_security_ip_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_id, _public_key, raw_secret = _setup_ingest(
        SessionLocal,
        username="security-ip",
        tenant_name="SecurityIp",
        domain="example.com",
    )

    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event_type": "login_attempt_failed",
        "severity": "medium",
        "request_path": "/login",
        "method": "POST",
        "status_code": 401,
    }
    resp = client.post(
        "/api/v1/ingest/security",
        json=payload,
        headers={
            "X-Api-Secret": raw_secret,
            "X-Forwarded-For": "198.51.100.10",
            "User-Agent": "agent-test/1.0",
        },
    )
    assert resp.status_code == 200

    with SessionLocal() as db:
        stored = db.query(SecurityEvent).filter_by(tenant_id=tenant_id).first()
        assert stored is not None
        assert stored.ip_hash is not None
        assert stored.user_agent == "agent-test/1.0"


def test_ingest_security_revoked_key_rejected():
    db_url = f"sqlite:///./ingest_security_revoked_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    _tenant_id, public_key, raw_secret = _setup_ingest(
        SessionLocal,
        username="security-revoked",
        tenant_name="SecurityRevoked",
        domain="example.com",
    )
    with SessionLocal() as db:
        key = db.query(APIKey).filter_by(public_key=public_key).first()
        key.revoked_at = datetime.now(timezone.utc)
        key.status = "revoked"
        db.commit()

    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event_type": "login_attempt_failed",
        "severity": "medium",
        "request_path": "/login",
    }
    resp = client.post(
        "/api/v1/ingest/security",
        json=payload,
        headers={"X-Api-Secret": raw_secret},
    )
    assert resp.status_code == 401
