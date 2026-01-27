import importlib.util
import os
from datetime import datetime
from types import SimpleNamespace
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
from app.core.config import settings
from app.core.security import get_password_hash
from app.crud.memberships import create_membership
from app.crud.tenants import create_tenant
from app.crud.users import create_user
from app.models.enums import RoleEnum
from app.models.incidents import Incident
from app.models.plans import Plan
from app.models.prescriptions import PrescriptionBundle, PrescriptionItem

from security_utils import assert_endpoint_requires_role


client = TestClient(app)


def _has_stripe() -> bool:
    return importlib.util.find_spec("stripe") is not None


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


def _seed_tenant(SessionLocal):
    with SessionLocal() as db:
        tenant = create_tenant(db, name="Role Templates")
        owner = create_user(db, username="owner@example.com", password_hash=get_password_hash("pw"))
        create_membership(db, tenant.id, owner.id, RoleEnum.OWNER)

        billing_admin = create_user(
            db, username="billing@example.com", password_hash=get_password_hash("pw")
        )
        security_admin = create_user(
            db, username="security@example.com", password_hash=get_password_hash("pw")
        )
        analyst = create_user(db, username="analyst@example.com", password_hash=get_password_hash("pw"))
        viewer = create_user(db, username="viewer@example.com", password_hash=get_password_hash("pw"))

        create_membership(db, tenant.id, billing_admin.id, RoleEnum.BILLING_ADMIN)
        create_membership(db, tenant.id, security_admin.id, RoleEnum.SECURITY_ADMIN)
        create_membership(db, tenant.id, analyst.id, RoleEnum.ANALYST)
        viewer_membership = create_membership(db, tenant.id, viewer.id, RoleEnum.VIEWER)
        db.commit()

        return {
            "tenant_id": tenant.id,
            "tenant_slug": tenant.slug,
            "owner": owner.username,
            "billing_admin": billing_admin.username,
            "security_admin": security_admin.username,
            "analyst": analyst.username,
            "viewer": viewer.username,
            "viewer_membership_id": viewer_membership.id,
        }


def _seed_billing_plan(db):
    free_plan = Plan(
        name="Free",
        price_monthly=0,
        limits_json={},
        features_json={},
        is_active=True,
    )
    pro_plan = Plan(
        name="Pro",
        price_monthly=149,
        limits_json={},
        features_json={},
        is_active=True,
    )
    db.add_all([free_plan, pro_plan])
    db.commit()


def test_billing_admin_can_access_billing_endpoints_only(monkeypatch):
    db_url = f"sqlite:///./role_billing_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        _seed_billing_plan(db)
    seed = _seed_tenant(SessionLocal)
    billing_token = _login(seed["billing_admin"], seed["tenant_slug"])
    owner_token = _login(seed["owner"], seed["tenant_slug"])

    if _has_stripe():
        settings.STRIPE_SECRET_KEY = "sk_test_role"
        settings.STRIPE_PRICE_ID_PRO = "price_pro_role"

        def _fake_create(**kwargs):
            return SimpleNamespace(url="https://checkout.test/session")

        monkeypatch.setattr("app.api.billing.stripe.checkout.Session.create", _fake_create)

        assert_endpoint_requires_role(
            client,
            "POST",
            "/api/v1/billing/checkout",
            allowed_token=billing_token,
            denied_token=_login(seed["security_admin"], seed["tenant_slug"]),
            tenant_header=seed["tenant_slug"],
            json_body={"plan_key": "pro"},
            expected_allowed={200},
        )

    denied_resp = client.get(
        "/api/v1/security/chain",
        headers={"Authorization": f"Bearer {billing_token}", "X-Tenant-ID": seed["tenant_slug"]},
    )
    assert denied_resp.status_code in {403, 404}

    allowed_resp = client.get(
        "/api/v1/security/chain",
        headers={"Authorization": f"Bearer {owner_token}", "X-Tenant-ID": seed["tenant_slug"]},
    )
    assert allowed_resp.status_code == 200


def test_security_admin_can_manage_security_but_not_billing(monkeypatch):
    db_url = f"sqlite:///./role_security_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        _seed_billing_plan(db)
    seed = _seed_tenant(SessionLocal)

    security_token = _login(seed["security_admin"], seed["tenant_slug"])
    owner_token = _login(seed["owner"], seed["tenant_slug"])

    security_resp = client.get(
        "/api/v1/security/chain",
        headers={"Authorization": f"Bearer {security_token}", "X-Tenant-ID": seed["tenant_slug"]},
    )
    assert security_resp.status_code == 200

    if _has_stripe():
        settings.STRIPE_SECRET_KEY = "sk_test_role_security"
        settings.STRIPE_PRICE_ID_PRO = "price_pro_security"

        def _fake_create(**kwargs):
            return SimpleNamespace(url="https://checkout.test/session")

        monkeypatch.setattr("app.api.billing.stripe.checkout.Session.create", _fake_create)

        assert_endpoint_requires_role(
            client,
            "POST",
            "/api/v1/billing/checkout",
            allowed_token=owner_token,
            denied_token=security_token,
            tenant_header=seed["tenant_slug"],
            json_body={"plan_key": "pro"},
            expected_allowed={200},
        )


def test_analyst_can_apply_prescriptions_but_cannot_manage_members():
    db_url = f"sqlite:///./role_analyst_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    seed = _seed_tenant(SessionLocal)

    with SessionLocal() as db:
        now = datetime.utcnow()
        incident = Incident(
            tenant_id=seed["tenant_id"],
            category="security",
            title="Suspicious traffic",
            severity="high",
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(incident)
        db.flush()
        bundle = PrescriptionBundle(
            tenant_id=seed["tenant_id"],
            incident_id=incident.id,
            items_json=[],
            status="suggested",
        )
        db.add(bundle)
        db.flush()
        item = PrescriptionItem(
            bundle_id=bundle.id,
            tenant_id=seed["tenant_id"],
            incident_id=incident.id,
            key="apply_waf_rule",
            title="Apply WAF rule",
            priority="P1",
            effort="medium",
            expected_effect="Reduce threat volume",
            status="suggested",
        )
        db.add(item)
        db.commit()
        item_id = item.id

    analyst_token = _login(seed["analyst"], seed["tenant_slug"])
    resp = client.patch(
        f"/api/v1/prescriptions/items/{item_id}",
        headers={"Authorization": f"Bearer {analyst_token}", "X-Tenant-ID": seed["tenant_slug"]},
        json={"status": "applied", "notes": "applied via analyst"},
    )
    assert resp.status_code == 200

    denied = client.patch(
        f"/api/v1/members/{seed['viewer_membership_id']}",
        headers={"Authorization": f"Bearer {analyst_token}", "X-Tenant-ID": seed["tenant_slug"]},
        json={"role": "viewer"},
    )
    assert denied.status_code in {403, 404}
