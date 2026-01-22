import json
import os
import time
import hmac
import hashlib
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
from app.crud.tenants import create_tenant_with_owner
from app.crud.users import create_user
from app.models.plans import Plan
from app.models.subscriptions import Subscription


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


def _build_stripe_signature(payload: str, secret: str, timestamp: int | None = None) -> str:
    ts = timestamp or int(time.time())
    signed_payload = f"{ts}.{payload}".encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={signature}"


def test_billing_checkout_creates_session_for_tenant(monkeypatch):
    db_url = f"sqlite:///./billing_checkout_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
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
        owner = create_user(db, username="owner", password_hash=get_password_hash("pw"))
        tenant, _ = create_tenant_with_owner(db, name="Acme", slug=None, owner_user=owner, plan=free_plan)
        db.commit()
        tenant_slug = tenant.slug
        tenant_id = tenant.id

    settings.STRIPE_SECRET_KEY = "sk_test_123"
    settings.STRIPE_PRICE_ID_PRO = "price_pro"

    def _fake_create(**kwargs):
        assert kwargs["line_items"][0]["price"] == "price_pro"
        assert kwargs["client_reference_id"] == str(tenant_id)
        return SimpleNamespace(url="https://checkout.test/session")

    monkeypatch.setattr("app.api.billing.stripe.checkout.Session.create", _fake_create)

    token = _login("owner", tenant_slug)
    resp = client.post(
        "/api/v1/billing/checkout",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
        json={"plan_key": "pro"},
    )
    assert resp.status_code == 200
    assert resp.json()["checkout_url"] == "https://checkout.test/session"


def test_billing_webhook_updates_tenant_subscription_status():
    db_url = f"sqlite:///./billing_webhook_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        plan = Plan(
            name="Pro",
            price_monthly=149,
            limits_json={},
            features_json={},
            is_active=True,
        )
        db.add(plan)
        db.commit()
        owner = create_user(db, username="owner2", password_hash=get_password_hash("pw"))
        tenant, _ = create_tenant_with_owner(db, name="Umbrella", slug=None, owner_user=owner, plan=plan)
        db.commit()
        tenant_id = tenant.id

    settings.STRIPE_WEBHOOK_SECRET = "whsec_test"
    settings.STRIPE_PRICE_ID_PRO = "price_pro"

    event = {
        "id": "evt_123",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_123",
                "customer": "cus_456",
                "status": "active",
                "current_period_start": 1700000000,
                "current_period_end": 1700600000,
                "cancel_at_period_end": False,
                "metadata": {"tenant_id": str(tenant_id), "plan_key": "pro"},
                "items": {"data": [{"price": {"id": "price_pro"}}]},
            }
        },
    }
    payload = json.dumps(event)
    signature = _build_stripe_signature(payload, settings.STRIPE_WEBHOOK_SECRET)
    resp = client.post(
        "/api/v1/billing/webhook",
        headers={"Stripe-Signature": signature},
        data=payload,
    )
    assert resp.status_code == 200

    with SessionLocal() as db:
        subscription = (
            db.query(Subscription)
            .filter(Subscription.tenant_id == tenant_id)
            .order_by(Subscription.id.desc())
            .first()
        )
        assert subscription is not None
        assert subscription.plan_key == "pro"
        assert subscription.status == "active"
        assert subscription.stripe_customer_id == "cus_456"
        assert subscription.stripe_subscription_id == "sub_123"


def test_billing_webhook_rejects_invalid_signature():
    settings.STRIPE_WEBHOOK_SECRET = "whsec_invalid"
    payload = json.dumps({"id": "evt_bad", "type": "invoice.paid", "data": {"object": {}}})
    resp = client.post(
        "/api/v1/billing/webhook",
        headers={"Stripe-Signature": "t=0,v1=bad"},
        data=payload,
    )
    assert resp.status_code == 400
