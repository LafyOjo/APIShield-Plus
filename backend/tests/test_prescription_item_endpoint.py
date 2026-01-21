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
from app.models.audit_logs import AuditLog
from app.models.enums import RoleEnum
from app.models.incidents import Incident
from app.models.prescriptions import PrescriptionBundle, PrescriptionItem


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
        evidence_json={"request_paths": {"/login": 3}},
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident.id


def _seed_prescription_item(
    db,
    *,
    tenant_id: int,
    website_id: int,
    env_id: int,
    incident_id: int,
):
    bundle = PrescriptionBundle(
        tenant_id=tenant_id,
        website_id=website_id,
        environment_id=env_id,
        incident_id=incident_id,
        status="suggested",
        items_json=[
            {
                "id": "login_hardening",
                "why_it_matters": "Login abuse erodes trust.",
                "steps": ["Enable rate limiting."],
                "automation_possible": True,
            }
        ],
    )
    db.add(bundle)
    db.flush()
    item = PrescriptionItem(
        bundle_id=bundle.id,
        tenant_id=tenant_id,
        website_id=website_id,
        environment_id=env_id,
        incident_id=incident_id,
        key="login_hardening",
        title="Harden login protections",
        priority="P1",
        effort="med",
        expected_effect="security",
        status="suggested",
        evidence_json={"paths": ["/login"]},
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item.id


def test_update_prescription_item_status_applied_sets_applied_at():
    db_url = f"sqlite:///./prescriptions_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    tenant_slug, tenant_id, user_id, website_id, env_id = _seed_tenant(
        SessionLocal,
        username="alice",
        tenant_name="Acme",
        domain="a.example.com",
    )

    with SessionLocal() as db:
        incident_id = _seed_incident(
            db,
            tenant_id=tenant_id,
            website_id=website_id,
            env_id=env_id,
            title="Login spike",
        )
        item_id = _seed_prescription_item(
            db,
            tenant_id=tenant_id,
            website_id=website_id,
            env_id=env_id,
            incident_id=incident_id,
        )

    token = _login("alice", tenant_slug)
    resp = client.patch(
        f"/api/v1/prescriptions/items/{item_id}",
        json={"status": "applied"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "applied"
    assert payload["applied_at"] is not None
    assert payload["dismissed_at"] is None
    assert payload["snoozed_until"] is None
    assert payload["applied_by_user_id"] == user_id

    with SessionLocal() as db:
        item = db.query(PrescriptionItem).filter(PrescriptionItem.id == item_id).first()
        assert item is not None
        assert item.status == "applied"
        assert item.applied_at is not None


def test_update_prescription_item_tenant_scoped():
    db_url = f"sqlite:///./prescriptions_scope_{uuid4().hex}.db"
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
        incident_id = _seed_incident(
            db,
            tenant_id=tenant_b_id,
            website_id=website_b_id,
            env_id=env_b_id,
            title="Credential stuffing",
        )
        item_id = _seed_prescription_item(
            db,
            tenant_id=tenant_b_id,
            website_id=website_b_id,
            env_id=env_b_id,
            incident_id=incident_id,
        )

    token = _login("alice", tenant_a_slug)
    resp = client.patch(
        f"/api/v1/prescriptions/items/{item_id}",
        json={"status": "dismissed"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_a_slug},
    )
    assert resp.status_code == 404


def test_update_prescription_item_creates_audit_log():
    db_url = f"sqlite:///./prescriptions_audit_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    tenant_slug, tenant_id, _user_id, website_id, env_id = _seed_tenant(
        SessionLocal,
        username="carol",
        tenant_name="Wayne",
        domain="example.com",
    )

    with SessionLocal() as db:
        incident_id = _seed_incident(
            db,
            tenant_id=tenant_id,
            website_id=website_id,
            env_id=env_id,
            title="Login abuse",
        )
        item_id = _seed_prescription_item(
            db,
            tenant_id=tenant_id,
            website_id=website_id,
            env_id=env_id,
            incident_id=incident_id,
        )

    token = _login("carol", tenant_slug)
    resp = client.patch(
        f"/api/v1/prescriptions/items/{item_id}",
        json={"status": "dismissed"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200

    with SessionLocal() as db:
        event_label = f"prescription_dismissed:{item_id}"
        audit = (
            db.query(AuditLog)
            .filter(AuditLog.tenant_id == tenant_id, AuditLog.event == event_label)
            .first()
        )
        assert audit is not None
