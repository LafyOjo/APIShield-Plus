import os
from datetime import datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("SKIP_MIGRATIONS", "1")

from app.main import app
import app.core.db as db_module
import app.core.access_log as access_log_module
import app.core.policy as policy_module
from app.core.db import Base
from app.core.security import get_password_hash
from app.crud.memberships import create_membership
from app.crud.tenants import create_tenant
from app.crud.users import create_user
from app.crud.websites import create_website
from app.crud.website_environments import list_environments
from app.models.behaviour_events import BehaviourEvent
from app.models.enums import RoleEnum


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


def test_onboarding_state_updates_on_step_complete(tmp_path):
    db_url = f"sqlite:///{tmp_path}/onboarding_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="owner-onboard", password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name="OnboardingTenant")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=owner.id,
            role=RoleEnum.OWNER,
            created_by_user_id=owner.id,
        )
        website = create_website(db, tenant.id, "example.com", created_by_user_id=owner.id)
        tenant_slug = tenant.slug

    token = _login("owner-onboard")
    resp = client.post(
        "/api/v1/onboarding/complete-step",
        json={"step": "create_website", "website_id": website.id},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert "create_website" in payload["completed_steps"]
    assert payload["first_website_id"] == website.id
    assert payload["current_step"] != "create_website"


def test_onboarding_verify_events_passes_when_recent_events_exist(tmp_path):
    db_url = f"sqlite:///{tmp_path}/onboarding_events_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="owner-events", password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name="OnboardingEventsTenant")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=owner.id,
            role=RoleEnum.OWNER,
            created_by_user_id=owner.id,
        )
        website = create_website(db, tenant.id, "events.example.com", created_by_user_id=owner.id)
        env_id = list_environments(db, website.id)[0].id
        event = BehaviourEvent(
            tenant_id=tenant.id,
            website_id=website.id,
            environment_id=env_id,
            ingested_at=datetime.utcnow(),
            event_ts=datetime.utcnow(),
            event_id="evt_1",
            event_type="page_view",
            url="https://events.example.com/",
            path="/",
            referrer=None,
            session_id="s_1",
            visitor_id=None,
            ip_hash=None,
            user_agent=None,
            meta={},
        )
        db.add(event)
        db.commit()
        tenant_slug = tenant.slug

    token = _login("owner-events")
    resp = client.post(
        "/api/v1/onboarding/complete-step",
        json={
            "step": "verify_events",
            "website_id": website.id,
            "environment_id": env_id,
        },
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert "verify_events" in payload["completed_steps"]
    assert payload["verified_event_received_at"] is not None
