import os
from datetime import datetime, timedelta
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
from app.core.db import Base
from app.core.security import get_password_hash
from app.crud.memberships import create_membership
from app.crud.tenants import create_tenant
from app.crud.subscriptions import set_tenant_plan
from app.crud.tenant_retention_policies import upsert_policy
from app.crud.users import create_user
from app.crud.websites import create_website
from app.jobs.retention import run_retention_for_tenant
from app.models.audit_logs import AuditLog
from app.models.behaviour_events import BehaviourEvent
from app.models.website_environments import WebsiteEnvironment
from app.models.plans import Plan


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
    Base.metadata.create_all(bind=engine)
    return SessionLocal


def _login(username: str) -> str:
    resp = client.post("/login", json={"username": username, "password": "pw"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _seed_behaviour_event(db, tenant_id: int, *, days_ago: int = 10) -> BehaviourEvent:
    website = create_website(db, tenant_id, "example.com")
    env = (
        db.query(WebsiteEnvironment)
        .filter(WebsiteEnvironment.website_id == website.id)
        .first()
    )
    past = datetime.utcnow() - timedelta(days=days_ago)
    event = BehaviourEvent(
        tenant_id=tenant_id,
        website_id=website.id,
        environment_id=env.id,
        ingested_at=past,
        event_ts=past,
        event_id=f"evt_{uuid4().hex}",
        event_type="page_view",
        url="https://example.com",
        path="/",
        session_id="s1",
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def test_legal_hold_prevents_retention_deletion():
    db_url = f"sqlite:///./retention_hold_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        tenant = create_tenant(db, name="LegalHold")
        _seed_behaviour_event(db, tenant.id, days_ago=15)
        upsert_policy(
            db,
            tenant.id,
            "behaviour_events",
            is_legal_hold_enabled=True,
            legal_hold_reason="investigation",
        )
        run_retention_for_tenant(db, tenant.id)
        remaining = (
            db.query(BehaviourEvent)
            .filter(BehaviourEvent.tenant_id == tenant.id)
            .count()
        )
        assert remaining == 1


def test_retention_policy_changes_affect_purge_cutoff():
    db_url = f"sqlite:///./retention_cutoff_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        tenant = create_tenant(db, name="RetentionChange")
        _seed_behaviour_event(db, tenant.id, days_ago=5)
        upsert_policy(db, tenant.id, "behaviour_events", retention_days=10)
        run_retention_for_tenant(db, tenant.id)
        assert (
            db.query(BehaviourEvent)
            .filter(BehaviourEvent.tenant_id == tenant.id)
            .count()
            == 1
        )
        upsert_policy(db, tenant.id, "behaviour_events", retention_days=1)
        run_retention_for_tenant(db, tenant.id)
        assert (
            db.query(BehaviourEvent)
            .filter(BehaviourEvent.tenant_id == tenant.id)
            .count()
            == 0
        )


def test_legal_hold_actions_audited():
    db_url = f"sqlite:///./retention_audit_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="owner_ret", password_hash=get_password_hash("pw"), role="user")
        plan = Plan(
            name="Enterprise",
            price_monthly=None,
            limits_json={"retention_days": 365},
            features_json={"legal_hold": True},
            is_active=True,
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)
        tenant = create_tenant(db, name="RetentionAudit")
        set_tenant_plan(db, tenant.id, plan.id)
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=owner.id,
            role="owner",
            created_by_user_id=owner.id,
        )
        tenant_slug = tenant.slug

    token = _login("owner_ret")
    resp = client.patch(
        "/api/v1/retention/policies",
        json={
            "dataset_key": "behaviour_events",
            "is_legal_hold_enabled": True,
            "legal_hold_reason": "investigation hold",
        },
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    with SessionLocal() as db:
        entries = (
            db.query(AuditLog)
            .filter(
                AuditLog.tenant_id == tenant.id,
                AuditLog.event.like("retention.legal_hold_enabled.%"),
            )
            .all()
        )
        assert entries
