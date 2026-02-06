import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
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
from app.core.usage import increment_events
from app.crud.api_keys import create_api_key
from app.crud.memberships import create_membership
from app.crud.tenant_settings import update_settings
from app.crud.tenants import create_tenant
from app.crud.users import create_user
from app.crud.website_environments import list_environments
from app.crud.websites import create_website
from app.models.behaviour_events import BehaviourEvent
from app.models.enums import RoleEnum
from app.models.tenant_usage import TenantUsage


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


def _event_payload(*, url: str, path: str):
    return {
        "event_id": str(uuid4()),
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": "page_view",
        "url": url,
        "path": path,
    }


def test_ingest_bulk_insert_used_for_batched_events():
    db_url = f"sqlite:///./ingest_batch_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    _tenant_id, _website_id, _env_id, api_key = _setup_ingest(
        SessionLocal,
        username="batch-user",
        tenant_name="BatchTenant",
        domain="example.com",
    )

    payload = {
        "events": [
            _event_payload(url="https://example.com/", path="/"),
            _event_payload(url="https://example.com/pricing", path="/pricing"),
        ]
    }
    resp = client.post(
        "/api/v1/ingest/browser",
        json=payload,
        headers={"X-Api-Key": api_key},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body.get("accepted") == 2

    with SessionLocal() as db:
        count = db.query(BehaviourEvent).count()
        assert count == 2


def test_sampling_rules_keep_checkout_events_full_rate():
    db_url = f"sqlite:///./ingest_sampling_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_id, _website_id, _env_id, api_key = _setup_ingest(
        SessionLocal,
        username="sample-user",
        tenant_name="SampleTenant",
        domain="example.com",
    )
    with SessionLocal() as db:
        update_settings(
            db,
            tenant_id,
            {
                "alert_prefs": {
                    "sampling": {
                        "default_rate": 0.0,
                        "rules": [
                            {"event_type": "page_view", "path_prefix": "/checkout", "sample_rate": 1.0}
                        ],
                    }
                }
            },
        )
        db.commit()

    payload = {
        "events": [
            _event_payload(url="https://example.com/checkout", path="/checkout"),
            _event_payload(url="https://example.com/pricing", path="/pricing"),
        ]
    }
    resp = client.post(
        "/api/v1/ingest/browser",
        json=payload,
        headers={"X-Api-Key": api_key},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("accepted") == 1
    assert body.get("sampled_out") == 1

    with SessionLocal() as db:
        rows = db.query(BehaviourEvent).all()
        assert len(rows) == 1
        assert rows[0].path == "/checkout"
        usage = db.query(TenantUsage).filter(TenantUsage.tenant_id == tenant_id).first()
        assert usage is not None
        assert usage.events_sampled_out == 1


def test_quota_exceeded_returns_429_and_records_metering(monkeypatch):
    db_url = f"sqlite:///./ingest_quota_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_id, _website_id, _env_id, api_key = _setup_ingest(
        SessionLocal,
        username="quota-user",
        tenant_name="QuotaTenant",
        domain="example.com",
    )

    def _entitlements(_db, _tenant_id, *args, **kwargs):
        return {"limits": {"events_per_month": 1}}

    monkeypatch.setattr("app.api.ingest.resolve_effective_entitlements", _entitlements)

    with SessionLocal() as db:
        increment_events(tenant_id, 1, db=db)

    payload = _event_payload(url="https://example.com/", path="/")
    resp = client.post(
        "/api/v1/ingest/browser",
        json=payload,
        headers={"X-Api-Key": api_key},
    )
    assert resp.status_code == 429
