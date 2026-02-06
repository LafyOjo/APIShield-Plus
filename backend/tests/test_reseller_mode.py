import os
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./reseller_test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("SKIP_MIGRATIONS", "1")

from app.main import app  # noqa: E402
import app.core.db as db_module  # noqa: E402
import app.core.access_log as access_log_module  # noqa: E402
import app.core.policy as policy_module  # noqa: E402
from app.core.db import Base  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402
from app.crud.affiliates import create_partner  # noqa: E402
from app.crud.resellers import create_reseller_account  # noqa: E402
from app.crud.tenants import create_tenant  # noqa: E402
from app.crud.users import create_user  # noqa: E402
from app.models.partners import PartnerUser  # noqa: E402
from app.models.plans import Plan  # noqa: E402
from app.models.resellers import ManagedTenant  # noqa: E402
from app.models.subscriptions import Subscription  # noqa: E402


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


def _seed_free_plan(db):
    plan = Plan(
        name="Free",
        price_monthly=0,
        limits_json={"websites": 1},
        features_json={},
        is_active=True,
    )
    db.add(plan)
    db.commit()
    return plan


def _login(username: str) -> str:
    resp = client.post("/login", json={"username": username, "password": "pw"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_reseller_can_create_tenant_and_link_managed_tenant():
    db_url = f"sqlite:///./reseller_create_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        _seed_free_plan(db)
        partner_user = create_user(db, username="reseller", password_hash=get_password_hash("pw"))
        partner = create_partner(
            db,
            name="Reseller Inc",
            code="reseller_inc",
            status="active",
            commission_type="flat",
            commission_value=50,
        )
        db.add(PartnerUser(partner_id=partner.id, user_id=partner_user.id, role="reseller_admin"))
        create_reseller_account(db, partner_id=partner.id, billing_mode="reseller_pays_invoice")
        db.commit()
        partner_id = partner.id

    token = _login("reseller")
    resp = client.post(
        "/api/v1/reseller/tenants",
        json={"name": "Acme Managed", "plan_key": "free"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    payload = resp.json()
    tenant_id = payload["tenant"]["tenant_id"]

    with SessionLocal() as db:
        managed = db.query(ManagedTenant).filter(ManagedTenant.tenant_id == tenant_id).first()
        assert managed is not None
        assert managed.reseller_partner_id == partner_id
        subscription = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
        assert subscription is not None
        assert subscription.provider == "reseller"


def test_reseller_cannot_view_customer_incident_details():
    db_url = f"sqlite:///./reseller_block_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        _seed_free_plan(db)
        partner_user = create_user(db, username="reseller2", password_hash=get_password_hash("pw"))
        partner = create_partner(
            db,
            name="Reseller Access",
            code="reseller_access",
            status="active",
            commission_type="flat",
            commission_value=50,
        )
        db.add(PartnerUser(partner_id=partner.id, user_id=partner_user.id, role="reseller_admin"))
        create_reseller_account(db, partner_id=partner.id, billing_mode="customer_pays_stripe")
        tenant = create_tenant(db, name="Customer Tenant")
        tenant_slug = tenant.slug
        db.commit()

    token = _login("reseller2")
    resp = client.get(
        "/api/v1/incidents",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 403
