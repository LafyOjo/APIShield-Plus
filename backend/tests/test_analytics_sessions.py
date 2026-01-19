import os
from datetime import datetime, timedelta, timezone
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
from app.core.security import get_password_hash
from app.crud.api_keys import create_api_key
from app.crud.memberships import create_membership
from app.crud.tenants import create_tenant
from app.crud.users import create_user
from app.crud.website_environments import list_environments
from app.crud.websites import create_website
from app.models.enums import RoleEnum


client = TestClient(app)


def _setup_db(db_url: str):
    from app.models.behaviour_sessions import BehaviourSession
    from app.core.rate_limit import reset_state

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


def _login(username: str) -> str:
    resp = client.post("/login", json={"username": username, "password": "pw"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _setup_tenant(SessionLocal, *, username: str, tenant_name: str, domain: str):
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
            name="Analytics Key",
            created_by_user_id=owner.id,
        )
        db.commit()
        return owner, tenant, website, environment, api_key.public_key


def _ingest(api_key: str, payload: dict):
    resp = client.post(
        "/api/v1/ingest/browser",
        json=payload,
        headers={"X-Api-Key": api_key},
    )
    assert resp.status_code == 200


def test_sessions_list_tenant_scoped():
    db_url = f"sqlite:///./analytics_sessions_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    owner, tenant_a, website_a, _env_a, api_key_a = _setup_tenant(
        SessionLocal,
        username="analytics-owner",
        tenant_name="AnalyticsTenantA",
        domain="a.example.com",
    )
    with SessionLocal() as db:
        tenant_b = create_tenant(db, name="AnalyticsTenantB")
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
            name="Analytics Key",
            created_by_user_id=owner.id,
        )
        api_key_b = api_key_b.public_key
        tenant_b_slug = tenant_b.slug

    _ingest(
        api_key_a,
        {
            "event_id": str(uuid4()),
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "page_view",
            "url": "https://a.example.com/home",
            "path": "/home",
            "session_id": "s_a",
        },
    )
    _ingest(
        api_key_b,
        {
            "event_id": str(uuid4()),
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "page_view",
            "url": "https://b.example.com/home",
            "path": "/home",
            "session_id": "s_b",
        },
    )

    token = _login("analytics-owner")
    resp = client.get(
        "/api/v1/analytics/sessions",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_a.slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    session_ids = {item["session_id"] for item in payload["items"]}
    assert session_ids == {"s_a"}

    resp = client.get(
        "/api/v1/analytics/sessions",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_b_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    session_ids = {item["session_id"] for item in payload["items"]}
    assert session_ids == {"s_b"}


def test_session_detail_404_cross_tenant():
    db_url = f"sqlite:///./analytics_session_detail_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    owner, tenant_a, _website_a, _env_a, _api_key_a = _setup_tenant(
        SessionLocal,
        username="analytics-cross",
        tenant_name="AnalyticsTenantA",
        domain="a.example.com",
    )
    with SessionLocal() as db:
        tenant_b = create_tenant(db, name="AnalyticsTenantB")
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
            name="Analytics Key",
            created_by_user_id=owner.id,
        )
        api_key_b = api_key_b.public_key

    _ingest(
        api_key_b,
        {
            "event_id": str(uuid4()),
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "page_view",
            "url": "https://b.example.com/home",
            "path": "/home",
            "session_id": "s_cross",
        },
    )

    token = _login("analytics-cross")
    resp = client.get(
        "/api/v1/analytics/sessions/s_cross",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_a.slug},
    )
    assert resp.status_code == 404


def test_session_events_ordered_by_timestamp():
    db_url = f"sqlite:///./analytics_session_events_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    _owner, tenant, _website, _env, api_key = _setup_tenant(
        SessionLocal,
        username="analytics-order",
        tenant_name="AnalyticsTenant",
        domain="example.com",
    )

    session_id = "s_order"
    ts_late = datetime.now(timezone.utc)
    ts_early = ts_late - timedelta(minutes=5)

    _ingest(
        api_key,
        {
            "event_id": str(uuid4()),
            "ts": ts_late.isoformat(),
            "type": "click",
            "url": "https://example.com/late",
            "path": "/late",
            "session_id": session_id,
        },
    )
    _ingest(
        api_key,
        {
            "event_id": str(uuid4()),
            "ts": ts_early.isoformat(),
            "type": "page_view",
            "url": "https://example.com/early",
            "path": "/early",
            "session_id": session_id,
        },
    )

    token = _login("analytics-order")
    resp = client.get(
        f"/api/v1/analytics/sessions/{session_id}/events",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant.slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    items = payload["items"]
    assert len(items) == 2
    assert items[0]["path"] == "/early"
    assert items[1]["path"] == "/late"
