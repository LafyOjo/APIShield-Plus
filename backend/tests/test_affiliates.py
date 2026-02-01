import os
from uuid import uuid4

os.environ["DATABASE_URL"] = f"sqlite:///./affiliate_{uuid4().hex}.db"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["SKIP_MIGRATIONS"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.core.db import SessionLocal, Base, engine  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402
from app.core.affiliates import process_affiliate_conversion, void_affiliate_commission  # noqa: E402
from app.crud.affiliates import create_partner  # noqa: E402
from app.crud.tenants import create_tenant_with_owner  # noqa: E402
from app.crud.subscriptions import set_tenant_plan  # noqa: E402
from app.models.affiliates import AffiliateAttribution, AffiliateCommissionLedger  # noqa: E402
from app.models.plans import Plan  # noqa: E402
from app.models.users import User  # noqa: E402


client = TestClient(app)
Base.metadata.create_all(bind=engine)


def _ensure_plan(db, name="Free", price=0):
    plan = db.query(Plan).filter(Plan.name == name).first()
    if plan:
        return plan
    plan = Plan(
        name=name,
        price_monthly=price,
        limits_json={"websites": 1},
        features_json={},
        is_active=True,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def _create_user_with_tenant(db, username: str):
    user = User(username=username, password_hash=get_password_hash("pw"), role="user")
    db.add(user)
    db.flush()
    tenant, _membership = create_tenant_with_owner(db, name=f"{username} Workspace", slug=None, owner_user=user)
    db.commit()
    db.refresh(user)
    db.refresh(tenant)
    return user, tenant


def test_affiliate_attribution_saved_on_signup_with_aff_code():
    with SessionLocal() as db:
        _ensure_plan(db, "Free")
        partner = create_partner(
            db,
            name="Creator",
            code="aff_creator",
            status="active",
            commission_type="percent",
            commission_value=15,
        )

    resp = client.post(
        "/register",
        json={
            "username": "affiliate_user@example.com",
            "password": "pw",
            "affiliate_code": "aff_creator",
            "affiliate_meta": {"utm_source": "youtube"},
        },
    )
    assert resp.status_code == 200
    tenant_id = resp.json()["active_tenant_id"]

    with SessionLocal() as db:
        attribution = (
            db.query(AffiliateAttribution)
            .filter(AffiliateAttribution.tenant_id == tenant_id)
            .first()
        )
        assert attribution is not None
        assert attribution.partner_id == partner.id


def test_commission_ledger_created_on_subscription_paid():
    with SessionLocal() as db:
        free_plan = _ensure_plan(db, "Free")
        pro_plan = _ensure_plan(db, "Pro", price=200)
        partner = create_partner(
            db,
            name="Partner",
            code="aff_partner",
            status="active",
            commission_type="flat",
            commission_value=50,
        )
        user, tenant = _create_user_with_tenant(db, "paiduser@example.com")
        # attribution
        from app.core.affiliates import record_affiliate_attribution
        record_affiliate_attribution(db, affiliate_code=partner.code, tenant_id=tenant.id, source_meta=None)
        set_tenant_plan(db, tenant_id=tenant.id, plan_id=pro_plan.id, status="active")
        ledger = process_affiliate_conversion(db, tenant_id=tenant.id, stripe_subscription_id="sub_123")
        assert ledger is not None

    with SessionLocal() as db:
        entry = db.query(AffiliateCommissionLedger).filter(AffiliateCommissionLedger.stripe_subscription_id == "sub_123").first()
        assert entry is not None
        assert entry.status == "pending"


def test_commission_voided_if_subscription_refunded_or_canceled_early():
    with SessionLocal() as db:
        _ensure_plan(db, "Free")
        partner = create_partner(
            db,
            name="VoidPartner",
            code="aff_void",
            status="active",
            commission_type="flat",
            commission_value=25,
        )
        user, tenant = _create_user_with_tenant(db, "voiduser@example.com")
        from app.core.affiliates import record_affiliate_attribution
        record_affiliate_attribution(db, affiliate_code=partner.code, tenant_id=tenant.id, source_meta=None)
        set_tenant_plan(db, tenant_id=tenant.id, plan_id=_ensure_plan(db, "Pro", price=100).id, status="active")
        ledger = process_affiliate_conversion(db, tenant_id=tenant.id, stripe_subscription_id="sub_void")
        assert ledger is not None
        voided = void_affiliate_commission(db, tenant_id=tenant.id, stripe_subscription_id="sub_void", reason="refund")
        assert voided is not None
        assert voided.status == "void"
        assert voided.void_reason == "refund"
