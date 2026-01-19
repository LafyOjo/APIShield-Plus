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
            name="Funnel Key",
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


def test_funnel_counts_and_conversion_correct():
    db_url = f"sqlite:///./analytics_funnel_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    _owner, tenant, website, environment, api_key = _setup_tenant(
        SessionLocal,
        username="funnel-owner",
        tenant_name="FunnelTenant",
        domain="example.com",
    )

    base_ts = datetime.now(timezone.utc)
    _ingest(
        api_key,
        {
            "event_id": str(uuid4()),
            "ts": base_ts.isoformat(),
            "type": "page_view",
            "url": "https://example.com/",
            "path": "/",
            "session_id": "s1",
        },
    )
    _ingest(
        api_key,
        {
            "event_id": str(uuid4()),
            "ts": (base_ts + timedelta(seconds=5)).isoformat(),
            "type": "page_view",
            "url": "https://example.com/pricing",
            "path": "/pricing",
            "session_id": "s1",
        },
    )
    _ingest(
        api_key,
        {
            "event_id": str(uuid4()),
            "ts": (base_ts + timedelta(seconds=10)).isoformat(),
            "type": "page_view",
            "url": "https://example.com/checkout",
            "path": "/checkout",
            "session_id": "s1",
        },
    )
    _ingest(
        api_key,
        {
            "event_id": str(uuid4()),
            "ts": (base_ts + timedelta(seconds=15)).isoformat(),
            "type": "form_submit",
            "url": "https://example.com/checkout",
            "path": "/checkout",
            "session_id": "s1",
        },
    )

    _ingest(
        api_key,
        {
            "event_id": str(uuid4()),
            "ts": (base_ts + timedelta(seconds=20)).isoformat(),
            "type": "page_view",
            "url": "https://example.com/",
            "path": "/",
            "session_id": "s2",
        },
    )
    _ingest(
        api_key,
        {
            "event_id": str(uuid4()),
            "ts": (base_ts + timedelta(seconds=25)).isoformat(),
            "type": "page_view",
            "url": "https://example.com/pricing",
            "path": "/pricing",
            "session_id": "s2",
        },
    )

    _ingest(
        api_key,
        {
            "event_id": str(uuid4()),
            "ts": (base_ts + timedelta(seconds=30)).isoformat(),
            "type": "page_view",
            "url": "https://example.com/",
            "path": "/",
            "session_id": "s3",
        },
    )

    token = _login("funnel-owner")
    resp = client.post(
        "/api/v1/analytics/funnel",
        json={
            "website_id": website.id,
            "env_id": environment.id,
            "from": (base_ts - timedelta(minutes=1)).isoformat(),
            "to": (base_ts + timedelta(minutes=1)).isoformat(),
            "steps": [
                {"type": "page_view", "path": "/"},
                {"type": "page_view", "path": "/pricing"},
                {"type": "page_view", "path": "/checkout"},
                {"type": "form_submit", "path": "/checkout"},
            ],
        },
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant.slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    steps = payload["steps"]
    counts = [step["count"] for step in steps]
    dropoffs = [step["dropoff"] for step in steps]
    assert counts == [3, 2, 1, 1]
    assert dropoffs == [1, 1, 0, 1]
    assert steps[0]["conversion_to_next"] == 2 / 3
    assert steps[1]["conversion_to_next"] == 1 / 2
    assert steps[2]["conversion_to_next"] == 1.0
    assert steps[3]["conversion_to_next"] is None


def test_funnel_tenant_scoped():
    db_url = f"sqlite:///./analytics_funnel_scope_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    owner, tenant_a, website_a, environment_a, api_key_a = _setup_tenant(
        SessionLocal,
        username="funnel-scope",
        tenant_name="FunnelTenantA",
        domain="a.example.com",
    )
    with SessionLocal() as db:
        tenant_b = create_tenant(db, name="FunnelTenantB")
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
            name="Funnel Key",
            created_by_user_id=owner.id,
        )
        api_key_b = api_key_b.public_key

    _ingest(
        api_key_a,
        {
            "event_id": str(uuid4()),
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "page_view",
            "url": "https://a.example.com/",
            "path": "/",
            "session_id": "s_a",
        },
    )
    _ingest(
        api_key_b,
        {
            "event_id": str(uuid4()),
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "page_view",
            "url": "https://b.example.com/",
            "path": "/",
            "session_id": "s_b",
        },
    )

    token = _login("funnel-scope")
    resp = client.post(
        "/api/v1/analytics/funnel",
        json={
            "website_id": website_a.id,
            "env_id": environment_a.id,
            "steps": [{"type": "page_view", "path": "/"}],
        },
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_a.slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["steps"][0]["count"] == 1


def test_funnel_rejects_invalid_steps():
    db_url = f"sqlite:///./analytics_funnel_invalid_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    _owner, tenant, website, environment, _api_key = _setup_tenant(
        SessionLocal,
        username="funnel-invalid",
        tenant_name="FunnelTenantInvalid",
        domain="example.com",
    )
    token = _login("funnel-invalid")
    resp = client.post(
        "/api/v1/analytics/funnel",
        json={
            "website_id": website.id,
            "env_id": environment.id,
            "steps": [{"type": "unknown_event", "path": "/"}],
        },
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant.slug},
    )
    assert resp.status_code == 422
