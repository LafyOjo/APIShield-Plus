import os
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("INTEGRATION_ENCRYPTION_KEY", "a" * 32)
os.environ["SKIP_MIGRATIONS"] = "1"

from app.main import app
import app.core.db as db_module
import app.core.access_log as access_log_module
import app.core.policy as policy_module
from app.core.config import settings
from app.core.security import get_password_hash
from app.crud.memberships import create_membership
from app.crud.subscriptions import set_tenant_plan
from app.crud.tenants import create_tenant_with_owner
from app.crud.users import create_user
from app.models.enums import RoleEnum
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


def test_create_channel_requires_owner_admin():
    db_url = f"sqlite:///./notification_channels_endpoint_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    with SessionLocal() as db:
        plan = Plan(
            name="Free",
            price_monthly=0,
            limits_json={"notification_channels": 1},
            features_json={},
            is_active=True,
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)

        owner = create_user(db, username="owner", password_hash=get_password_hash("pw"))
        tenant, _ = create_tenant_with_owner(
            db,
            name="Acme",
            slug=None,
            owner_user=owner,
        )
        viewer = create_user(db, username="viewer", password_hash=get_password_hash("pw"))
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=viewer.id,
            role=RoleEnum.VIEWER,
            created_by_user_id=owner.id,
        )
        set_tenant_plan(db, tenant.id, plan.id)
        db.commit()
        tenant_slug = tenant.slug

    token = _login("viewer", tenant_slug)
    resp = client.post(
        "/api/v1/notifications/channels",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
        json={
            "type": "slack",
            "name": "Ops Slack",
            "config_secret": {
                "webhook_url": "https://hooks.slack.com/services/T000/B000/SECRET",
            },
        },
    )
    expected = 404 if settings.TENANT_STRICT_404 else 403
    assert resp.status_code == expected


def test_create_rule_enforces_entitlement_limits():
    db_url = f"sqlite:///./notification_rules_endpoint_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    with SessionLocal() as db:
        plan = Plan(
            name="Pro",
            price_monthly=249,
            limits_json={"notification_rules": 1},
            features_json={},
            is_active=True,
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)

        owner = create_user(db, username="owner2", password_hash=get_password_hash("pw"))
        tenant, _ = create_tenant_with_owner(
            db,
            name="Umbrella",
            slug=None,
            owner_user=owner,
            plan=plan,
        )
        set_tenant_plan(db, tenant.id, plan.id)
        db.commit()
        tenant_slug = tenant.slug

    token = _login("owner2", tenant_slug)
    resp = client.post(
        "/api/v1/notifications/rules",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
        json={"name": "Incidents", "trigger_type": "incident_created"},
    )
    assert resp.status_code == 200
    second = client.post(
        "/api/v1/notifications/rules",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
        json={"name": "Secondary", "trigger_type": "incident_created"},
    )
    assert second.status_code == 402
