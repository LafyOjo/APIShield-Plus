import os
from datetime import datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./partner_test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("SKIP_MIGRATIONS", "1")

from app.main import app
import app.core.db as db_module
import app.core.access_log as access_log_module
import app.core.policy as policy_module
from app.core.db import Base
from app.core.security import get_password_hash
from app.crud.affiliates import create_partner
from app.crud.tenants import create_tenant_with_owner
from app.crud.users import create_user
from app.models.activation_metrics import ActivationMetric
from app.models.affiliates import AffiliateAttribution, AffiliateCommissionLedger
from app.models.partners import PartnerLead, PartnerUser
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


def test_partner_user_cannot_access_tenant_private_endpoints():
    db_url = f"sqlite:///./partner_block_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        _seed_free_plan(db)
        owner = create_user(db, username="owner", password_hash=get_password_hash("pw"))
        tenant, _ = create_tenant_with_owner(db, name="Tenant A", slug=None, owner_user=owner)
        partner_user = create_user(db, username="partner", password_hash=get_password_hash("pw"))
        partner = create_partner(
            db,
            name="Partner Inc",
            code="aff_partner",
            status="active",
            commission_type="percent",
            commission_value=10,
        )
        db.add(PartnerUser(partner_id=partner.id, user_id=partner_user.id, role="admin"))
        db.commit()
        tenant_slug = tenant.slug

    token = _login("partner")
    resp = client.get(
        "/api/v1/websites",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 403


def test_partner_metrics_aggregate_correctly():
    db_url = f"sqlite:///./partner_metrics_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    now = datetime.utcnow()
    with SessionLocal() as db:
        _seed_free_plan(db)
        partner_user = create_user(db, username="partner2", password_hash=get_password_hash("pw"))
        partner = create_partner(
            db,
            name="Partner Metrics",
            code="aff_metrics",
            status="active",
            commission_type="flat",
            commission_value=25,
        )
        db.add(PartnerUser(partner_id=partner.id, user_id=partner_user.id, role="admin"))

        owner = create_user(db, username="owner2", password_hash=get_password_hash("pw"))
        tenant_a, _ = create_tenant_with_owner(db, name="Tenant A", slug=None, owner_user=owner)
        tenant_b, _ = create_tenant_with_owner(db, name="Tenant B", slug=None, owner_user=owner)

        db.add(
            AffiliateAttribution(
                partner_id=partner.id,
                tenant_id=tenant_a.id,
                first_touch_at=now,
                last_touch_at=now,
                source_meta_json={"utm_source": "email"},
            )
        )
        db.add(
            AffiliateAttribution(
                partner_id=partner.id,
                tenant_id=tenant_b.id,
                first_touch_at=now,
                last_touch_at=now,
                source_meta_json={"utm_source": "events"},
            )
        )
        db.add(
            ActivationMetric(
                tenant_id=tenant_a.id,
                time_to_first_event_seconds=120,
                activation_score=80,
            )
        )
        db.add(
            AffiliateCommissionLedger(
                partner_id=partner.id,
                tenant_id=tenant_a.id,
                stripe_subscription_id="sub_123",
                amount=50,
                currency="GBP",
                status="pending",
                earned_at=now,
            )
        )
        db.add(
            PartnerLead(
                partner_id=partner.id,
                lead_id="lead_abc",
                status="new",
                source_meta_json={"utm_campaign": "spring"},
            )
        )
        db.commit()

    token = _login("partner2")
    resp = client.get(
        "/api/v1/partners/metrics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["leads"] == 1
    assert payload["signups"] == 2
    assert payload["activated"] == 1
    assert payload["conversions"] == 1
    assert payload["commission_pending"] == 50.0
