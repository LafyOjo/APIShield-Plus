import os
from uuid import uuid4

os.environ["DATABASE_URL"] = f"sqlite:///./referral_{uuid4().hex}.db"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["SKIP_MIGRATIONS"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.core.db import SessionLocal, Base, engine  # noqa: E402
from app.core.referrals import process_referral_conversion  # noqa: E402
from app.crud.referrals import get_effective_program_config, create_referral_invite  # noqa: E402
from app.models.plans import Plan  # noqa: E402
from app.models.referrals import ReferralRedemption, CreditLedger  # noqa: E402
from app.models.users import User  # noqa: E402
from app.crud.tenants import create_tenant_with_owner  # noqa: E402
from app.crud.subscriptions import set_tenant_plan  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402


client = TestClient(app)
Base.metadata.create_all(bind=engine)


def _ensure_plan(db, name="Free", price=0, limits=None, features=None):
    plan = db.query(Plan).filter(Plan.name == name).first()
    if plan:
        return plan
    plan = Plan(
        name=name,
        price_monthly=price,
        limits_json=limits or {"websites": 1},
        features_json=features or {},
        is_active=True,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def _create_referrer(db, username: str):
    user = User(username=username, password_hash=get_password_hash("pw"), role="user")
    db.add(user)
    db.flush()
    tenant, _membership = create_tenant_with_owner(db, name=f"{username}'s Space", slug=None, owner_user=user)
    db.commit()
    db.refresh(user)
    db.refresh(tenant)
    return user, tenant


def test_referral_code_creates_pending_redemption_on_signup():
    with SessionLocal() as db:
        _ensure_plan(db, "Free")
        config = get_effective_program_config(db)
        config.is_enabled = True
        config.reward_type = "credit_gbp"
        config.reward_value = 50
        db.commit()

        referrer_user, referrer_tenant = _create_referrer(db, "referrer@example.com")
        invite = create_referral_invite(
            db,
            tenant_id=referrer_tenant.id,
            created_by_user_id=referrer_user.id,
            code="ref_testcode",
            expires_at=None,
            max_uses=20,
        )

    resp = client.post(
        "/register",
        json={"username": "newuser@example.com", "password": "pw", "referral_code": invite.code},
    )
    assert resp.status_code == 200

    with SessionLocal() as db:
        new_tenant_id = resp.json()["active_tenant_id"]
        redemption = (
            db.query(ReferralRedemption)
            .filter(ReferralRedemption.new_tenant_id == new_tenant_id)
            .first()
        )
        assert redemption is not None
        assert redemption.status == "pending"
        invite_db = db.query(type(invite)).filter(type(invite).id == invite.id).first()
        assert invite_db.uses_count == 1


def test_reward_applies_only_after_paid_subscription_active():
    with SessionLocal() as db:
        _ensure_plan(db, "Free")
        pro_plan = _ensure_plan(db, "Pro", price=100, limits={"websites": 5}, features={})
        pro_plan_id = pro_plan.id
        config = get_effective_program_config(db)
        config.is_enabled = True
        config.reward_type = "credit_gbp"
        config.reward_value = 75
        db.commit()

        referrer_user, referrer_tenant = _create_referrer(db, "referrer2@example.com")
        invite = create_referral_invite(
            db,
            tenant_id=referrer_tenant.id,
            created_by_user_id=referrer_user.id,
            code="ref_paid",
            expires_at=None,
            max_uses=20,
        )

    resp = client.post(
        "/register",
        json={"username": "paiduser@example.com", "password": "pw", "referral_code": invite.code},
    )
    assert resp.status_code == 200
    new_tenant_id = resp.json()["active_tenant_id"]

    with SessionLocal() as db:
        redemption = (
            db.query(ReferralRedemption)
            .filter(ReferralRedemption.new_tenant_id == new_tenant_id)
            .first()
        )
        assert redemption.status == "pending"
        set_tenant_plan(db, tenant_id=new_tenant_id, plan_id=pro_plan_id, status="active")
        process_referral_conversion(db, new_tenant_id=new_tenant_id)

        updated = db.query(ReferralRedemption).filter(ReferralRedemption.id == redemption.id).first()
        assert updated.status == "applied"
        ledger = db.query(CreditLedger).filter(CreditLedger.tenant_id == invite.tenant_id).all()
        assert ledger


def test_self_referral_blocked_by_policy_rules():
    with SessionLocal() as db:
        _ensure_plan(db, "Free")
        config = get_effective_program_config(db)
        config.is_enabled = True
        config.fraud_limits_json = {"block_same_email_domain": True, "max_redemptions_per_month": 5}
        db.commit()

        referrer_user, referrer_tenant = _create_referrer(db, "owner@example.com")
        invite = create_referral_invite(
            db,
            tenant_id=referrer_tenant.id,
            created_by_user_id=referrer_user.id,
            code="ref_self",
            expires_at=None,
            max_uses=20,
        )

    resp = client.post(
        "/register",
        json={"username": "another@example.com", "password": "pw", "referral_code": invite.code},
    )
    assert resp.status_code == 200

    with SessionLocal() as db:
        new_tenant_id = resp.json()["active_tenant_id"]
        redemption = (
            db.query(ReferralRedemption)
            .filter(ReferralRedemption.new_tenant_id == new_tenant_id)
            .first()
        )
        assert redemption is not None
        assert redemption.status == "rejected"
        assert redemption.reason in {"same_email_domain", "self_referral", "same_tenant_name"}
