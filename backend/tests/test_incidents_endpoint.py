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
import app.core.access_log as access_log_module
import app.core.db as db_module
import app.core.policy as policy_module
from app.core.security import get_password_hash
from app.crud.memberships import create_membership
from app.crud.tenants import create_tenant
from app.crud.users import create_user
from app.crud.website_environments import list_environments
from app.crud.websites import create_website
from app.models.enums import RoleEnum
from app.models.incidents import Incident


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
        return tenant.slug, tenant.id, website.id, env.id


def _seed_incident(db, *, tenant_id: int, website_id: int, env_id: int, title: str):
    now = datetime.utcnow()
    incident = Incident(
        tenant_id=tenant_id,
        website_id=website_id,
        environment_id=env_id,
        status="open",
        category="login",
        title=title,
        summary=None,
        severity="medium",
        first_seen_at=now - timedelta(hours=1),
        last_seen_at=now,
        primary_ip_hash="hash123",
        primary_country_code="US",
        evidence_json={"request_paths": {"/login": 3}, "event_types": {"login_attempt": 3}},
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident.id


def test_incidents_endpoints_tenant_scoped():
    db_url = f"sqlite:///./incidents_endpoint_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    tenant_a_slug, tenant_a_id, website_a_id, env_a_id = _seed_tenant(
        SessionLocal,
        username="alice",
        tenant_name="Acme",
        domain="a.example.com",
    )
    tenant_b_slug, tenant_b_id, website_b_id, env_b_id = _seed_tenant(
        SessionLocal,
        username="bob",
        tenant_name="Umbrella",
        domain="b.example.com",
    )

    with SessionLocal() as db:
        incident_a_id = _seed_incident(
            db,
            tenant_id=tenant_a_id,
            website_id=website_a_id,
            env_id=env_a_id,
            title="Login spike",
        )
        incident_b_id = _seed_incident(
            db,
            tenant_id=tenant_b_id,
            website_id=website_b_id,
            env_id=env_b_id,
            title="Credential stuffing",
        )

    token = _login("alice", tenant_a_slug)
    resp = client.get(
        "/api/v1/incidents",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_a_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload) == 1
    assert payload[0]["id"] == incident_a_id

    detail_resp = client.get(
        f"/api/v1/incidents/{incident_a_id}",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_a_slug},
    )
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["id"] == incident_a_id
    assert detail["map_link_params"]["country_code"] == "US"

    forbidden_resp = client.get(
        f"/api/v1/incidents/{incident_b_id}",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_a_slug},
    )
    assert forbidden_resp.status_code == 404
