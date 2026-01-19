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
from app.core.config import settings
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
            name="Rate Key",
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
    }


def test_ingest_rate_limit_per_public_key():
    reset_state()
    db_url = f"sqlite:///./ingest_rate_key_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_id, public_key = _setup_ingest(
        SessionLocal,
        username="rate-key",
        tenant_name="RateKeyTenant",
        domain="example.com",
    )
    with SessionLocal() as db:
        plan = Plan(
            name="LowIngest",
            price_monthly=0,
            limits_json={"ingest_rpm": 2, "ingest_burst": 2},
            features_json={},
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)
        set_tenant_plan(db, tenant_id, plan.id)

    for _ in range(2):
        resp = client.post(
            "/api/v1/ingest/browser",
            json=_payload("https://example.com/"),
            headers={"X-Api-Key": public_key},
        )
        assert resp.status_code == 200

    resp = client.post(
        "/api/v1/ingest/browser",
        json=_payload("https://example.com/"),
        headers={"X-Api-Key": public_key},
    )
    assert resp.status_code == 429


def test_ingest_rate_limit_per_ip_hash(monkeypatch):
    reset_state()
    monkeypatch.setattr(settings, "INGEST_IP_RPM", 2)
    monkeypatch.setattr(settings, "INGEST_IP_BURST", 2)

    db_url = f"sqlite:///./ingest_rate_ip_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_id, public_key = _setup_ingest(
        SessionLocal,
        username="rate-ip",
        tenant_name="RateIpTenant",
        domain="example.com",
    )
    with SessionLocal() as db:
        plan = Plan(
            name="HighIngest",
            price_monthly=0,
            limits_json={"ingest_rpm": 100, "ingest_burst": 100},
            features_json={},
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)
        set_tenant_plan(db, tenant_id, plan.id)

    for _ in range(2):
        resp = client.post(
            "/api/v1/ingest/browser",
            json=_payload("https://example.com/"),
            headers={
                "X-Api-Key": public_key,
                "X-Forwarded-For": "198.51.100.10",
            },
        )
        assert resp.status_code == 200

    resp = client.post(
        "/api/v1/ingest/browser",
        json=_payload("https://example.com/"),
        headers={
            "X-Api-Key": public_key,
            "X-Forwarded-For": "198.51.100.10",
        },
    )
    assert resp.status_code == 429


def test_ingest_rate_limits_respect_entitlement_limits():
    reset_state()
    db_url = f"sqlite:///./ingest_rate_plan_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_a_id, key_a = _setup_ingest(
        SessionLocal,
        username="plan-a",
        tenant_name="PlanA",
        domain="plan-a.com",
    )
    tenant_b_id, key_b = _setup_ingest(
        SessionLocal,
        username="plan-b",
        tenant_name="PlanB",
        domain="plan-b.com",
    )
    with SessionLocal() as db:
        plan_a = Plan(
            name="PlanLow",
            price_monthly=0,
            limits_json={"ingest_rpm": 1, "ingest_burst": 1},
            features_json={},
        )
        plan_b = Plan(
            name="PlanHigh",
            price_monthly=0,
            limits_json={"ingest_rpm": 3, "ingest_burst": 3},
            features_json={},
        )
        db.add(plan_a)
        db.add(plan_b)
        db.commit()
        db.refresh(plan_a)
        db.refresh(plan_b)
        set_tenant_plan(db, tenant_a_id, plan_a.id)
        set_tenant_plan(db, tenant_b_id, plan_b.id)

    resp = client.post(
        "/api/v1/ingest/browser",
        json=_payload("https://plan-a.com/"),
        headers={"X-Api-Key": key_a},
    )
    assert resp.status_code == 200
    resp = client.post(
        "/api/v1/ingest/browser",
        json=_payload("https://plan-a.com/"),
        headers={"X-Api-Key": key_a},
    )
    assert resp.status_code == 429

    for _ in range(2):
        resp = client.post(
            "/api/v1/ingest/browser",
            json=_payload("https://plan-b.com/"),
            headers={"X-Api-Key": key_b},
        )
        assert resp.status_code == 200
