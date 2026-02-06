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
from app.core.rate_limit import reset_state
from app.core.security import get_password_hash
from app.crud.api_keys import create_api_key
from app.crud.memberships import create_membership
from app.crud.subscriptions import set_tenant_plan
from app.crud.tenants import create_tenant
from app.crud.users import create_user
from app.crud.website_environments import list_environments
from app.crud.websites import create_website
from app.models.enums import RoleEnum
from app.models.plans import Plan
from app.models.tenant_usage import TenantUsage


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
            name="Meter Key",
            created_by_user_id=owner.id,
        )
        db.commit()
        return tenant.id, api_key.public_key


def _payload(url: str):
    return {
        "event_id": str(uuid4()),
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": "page_view",
        "url": url,
        "path": "/",
        "meta": {"a": 1},
    }


def test_ingest_increments_tenant_usage():
    db_url = f"sqlite:///./ingest_usage_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_id, public_key = _setup_ingest(
        SessionLocal,
        username="usage-user",
        tenant_name="UsageTenant",
        domain="usage.example.com",
    )
    with SessionLocal() as db:
        plan = Plan(
            name="Free",
            price_monthly=0,
            limits_json={"events_per_month": 100, "ingest_rpm": 100, "ingest_burst": 100},
            features_json={},
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)
        set_tenant_plan(db, tenant_id, plan.id)

    resp = client.post(
        "/api/v1/ingest/browser",
        json=_payload("https://usage.example.com/"),
        headers={"X-Api-Key": public_key},
    )
    assert resp.status_code == 200

    with SessionLocal() as db:
        usage = db.query(TenantUsage).filter(TenantUsage.tenant_id == tenant_id).first()
        assert usage is not None
        assert usage.events_ingested >= 1


def test_ingest_blocks_when_over_limit_free_plan():
    db_url = f"sqlite:///./ingest_quota_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_id, public_key = _setup_ingest(
        SessionLocal,
        username="quota-user",
        tenant_name="QuotaTenant",
        domain="quota.example.com",
    )
    with SessionLocal() as db:
        plan = Plan(
            name="Free",
            price_monthly=0,
            limits_json={"events_per_month": 1, "ingest_rpm": 100, "ingest_burst": 100},
            features_json={},
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)
        set_tenant_plan(db, tenant_id, plan.id)

    resp = client.post(
        "/api/v1/ingest/browser",
        json=_payload("https://quota.example.com/"),
        headers={"X-Api-Key": public_key},
    )
    assert resp.status_code == 200
    resp = client.post(
        "/api/v1/ingest/browser",
        json=_payload("https://quota.example.com/"),
        headers={"X-Api-Key": public_key},
    )
    assert resp.status_code == 429


def test_storage_bytes_estimate_increments_if_enabled():
    db_url = f"sqlite:///./ingest_storage_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_id, public_key = _setup_ingest(
        SessionLocal,
        username="storage-user",
        tenant_name="StorageTenant",
        domain="storage.example.com",
    )
    with SessionLocal() as db:
        plan = Plan(
            name="Free",
            price_monthly=0,
            limits_json={"events_per_month": 100, "ingest_rpm": 100, "ingest_burst": 100},
            features_json={},
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)
        set_tenant_plan(db, tenant_id, plan.id)

    resp = client.post(
        "/api/v1/ingest/browser",
        json=_payload("https://storage.example.com/"),
        headers={"X-Api-Key": public_key},
    )
    assert resp.status_code == 200

    with SessionLocal() as db:
        usage = db.query(TenantUsage).filter(TenantUsage.tenant_id == tenant_id).first()
        assert usage is not None
        assert usage.storage_bytes >= 1


def test_ingest_dedupe_does_not_increment_usage_twice():
    db_url = f"sqlite:///./ingest_dedupe_usage_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_id, public_key = _setup_ingest(
        SessionLocal,
        username="dedupe-user",
        tenant_name="DedupeTenant",
        domain="dedupe.example.com",
    )
    with SessionLocal() as db:
        plan = Plan(
            name="Free",
            price_monthly=0,
            limits_json={"events_per_month": 100, "ingest_rpm": 100, "ingest_burst": 100},
            features_json={},
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)
        set_tenant_plan(db, tenant_id, plan.id)

    event_id = str(uuid4())
    payload = {
        "event_id": event_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": "page_view",
        "url": "https://dedupe.example.com/",
        "path": "/",
    }
    resp = client.post(
        "/api/v1/ingest/browser",
        json=payload,
        headers={"X-Api-Key": public_key},
    )
    assert resp.status_code == 200
    resp = client.post(
        "/api/v1/ingest/browser",
        json=payload,
        headers={"X-Api-Key": public_key},
    )
    assert resp.status_code == 200

    with SessionLocal() as db:
        usage = db.query(TenantUsage).filter(TenantUsage.tenant_id == tenant_id).first()
        assert usage is not None
        assert usage.events_ingested == 1
