import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ["SKIP_MIGRATIONS"] = "1"

from app.main import app
import app.core.db as db_module
import app.core.access_log as access_log_module
import app.core.policy as policy_module
from app.core.privacy import hash_ip
from app.core.security import get_password_hash
from app.crud.memberships import create_membership
from app.crud.subscriptions import set_tenant_plan
from app.crud.tenants import create_tenant
from app.crud.users import create_user
from app.crud.website_environments import list_environments
from app.crud.websites import create_website
from app.models.enums import RoleEnum
from app.models.plans import Plan
from app.models.security_events import SecurityEvent
from app.security.taxonomy import SecurityEventTypeEnum, get_category, get_severity


client = TestClient(app)


def _setup_db(db_url: str):
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


def _login(username: str, tenant_slug: str) -> str:
    resp = client.post(
        "/login",
        json={"username": username, "password": "pw"},
        headers={"X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _seed_tenant(SessionLocal, *, username: str, tenant_name: str, domain: str):
    with SessionLocal() as db:
        user = create_user(db, username=username, password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name=tenant_name)
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=user.id,
            role=RoleEnum.OWNER,
            created_by_user_id=user.id,
        )
        website = create_website(db, tenant.id, domain, created_by_user_id=user.id)
        env = list_environments(db, website.id)[0]
        db.commit()
        return tenant.slug, tenant.id, user.id, website.id, env.id


def _set_plan(db, *, tenant_id: int, name: str, geo_map: bool, geo_days: int):
    plan = Plan(
        name=name,
        price_monthly=99,
        limits_json={"geo_history_days": geo_days},
        features_json={"geo_map": geo_map},
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    set_tenant_plan(db, tenant_id, plan.id)


def _seed_event(
    db,
    *,
    tenant_id: int,
    website_id: int,
    env_id: int,
    ip_hash: str,
    event_type: SecurityEventTypeEnum,
    event_ts: datetime,
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
            ip_hash=ip_hash,
            request_path="/login",
        )
    )


def test_security_events_endpoint_tenant_scoped():
    db_url = f"sqlite:///./security_events_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_a_slug, tenant_a_id, _user_a_id, website_a_id, env_a_id = _seed_tenant(
        SessionLocal,
        username="alice",
        tenant_name="Acme",
        domain="a.example.com",
    )
    tenant_b_slug, tenant_b_id, _user_b_id, website_b_id, env_b_id = _seed_tenant(
        SessionLocal,
        username="bob",
        tenant_name="Umbrella",
        domain="b.example.com",
    )
    with SessionLocal() as db:
        _set_plan(db, tenant_id=tenant_a_id, name="GeoProA", geo_map=True, geo_days=7)
        _set_plan(db, tenant_id=tenant_b_id, name="GeoProB", geo_map=True, geo_days=7)
        now = datetime.now(timezone.utc)
        _seed_event(
            db,
            tenant_id=tenant_a_id,
            website_id=website_a_id,
            env_id=env_a_id,
            ip_hash=hash_ip(tenant_a_id, "203.0.113.20"),
            event_type=SecurityEventTypeEnum.LOGIN_ATTEMPT_FAILED,
            event_ts=now,
        )
        _seed_event(
            db,
            tenant_id=tenant_b_id,
            website_id=website_b_id,
            env_id=env_b_id,
            ip_hash=hash_ip(tenant_b_id, "203.0.113.21"),
            event_type=SecurityEventTypeEnum.SQL_INJECTION_ATTEMPT,
            event_ts=now,
        )
        db.commit()

    token = _login("alice", tenant_a_slug)
    resp = client.get(
        "/api/v1/security/events",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_a_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] == 1
    assert len(payload["items"]) == 1
    item = payload["items"][0]
    assert item["category"] == "login"
    assert item["ip_hash"] and item["ip_hash"] != hash_ip(tenant_a_id, "203.0.113.20")


def test_security_events_endpoint_filters_by_category_and_time():
    db_url = f"sqlite:///./security_events_filters_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_slug, tenant_id, _user_id, website_id, env_id = _seed_tenant(
        SessionLocal,
        username="carol",
        tenant_name="Wayne",
        domain="example.com",
    )
    with SessionLocal() as db:
        _set_plan(db, tenant_id=tenant_id, name="GeoProC", geo_map=True, geo_days=7)
        now = datetime.now(timezone.utc)
        recent = now - timedelta(hours=2)
        older = now - timedelta(days=2)
        _seed_event(
            db,
            tenant_id=tenant_id,
            website_id=website_id,
            env_id=env_id,
            ip_hash=hash_ip(tenant_id, "203.0.113.22"),
            event_type=SecurityEventTypeEnum.LOGIN_ATTEMPT_FAILED,
            event_ts=recent,
        )
        _seed_event(
            db,
            tenant_id=tenant_id,
            website_id=website_id,
            env_id=env_id,
            ip_hash=hash_ip(tenant_id, "203.0.113.23"),
            event_type=SecurityEventTypeEnum.SQL_INJECTION_ATTEMPT,
            event_ts=older,
        )
        db.commit()

    token = _login("carol", tenant_slug)
    resp = client.get(
        "/api/v1/security/events",
        params={
            "category": "login",
            "from": (now - timedelta(hours=6)).isoformat(),
            "to": now.isoformat(),
        },
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] == 1
    assert payload["items"][0]["category"] == "login"
