from __future__ import annotations

import secrets

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import utcnow
from app.crud.referrals import (
    DEFAULT_FRAUD_LIMITS,
    DEFAULT_ELIGIBILITY_RULES,
    count_recent_redemptions,
    create_credit_entry,
    create_referral_redemption,
    get_effective_program_config,
    get_referral_invite_by_code,
    get_redemption_for_new_tenant,
    increment_invite_use,
)
from app.crud.subscriptions import get_active_subscription_for_tenant
from app.models.referrals import ReferralInvite, ReferralRedemption
from app.models.tenants import Tenant
from app.models.users import User


ALLOWED_REWARD_TYPES = {"credit_gbp", "discount_percent", "free_month"}


def generate_referral_code() -> str:
    token = secrets.token_urlsafe(8).replace("-", "").replace("_", "")
    return f"ref_{token.lower()}"


def build_share_url(code: str) -> str:
    base = settings.APP_BASE_URL or settings.FRONTEND_BASE_URL or "http://localhost:3000"
    return f"{base.rstrip('/')}/signup?ref={code}"


def _email_domain(username: str | None) -> str | None:
    if not username or "@" not in username:
        return None
    return username.split("@", 1)[1].strip().lower() or None


def _normalize_name(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().lower() or None


def _fraud_block_reason(
    *,
    config_fraud: dict,
    referrer_user: User | None,
    new_user: User,
    referrer_tenant: Tenant | None,
    new_tenant: Tenant,
    recent_redemptions: int,
) -> str | None:
    if referrer_user and referrer_user.id == new_user.id:
        return "self_referral"

    if config_fraud.get("block_same_email_domain", True):
        ref_domain = _email_domain(referrer_user.username if referrer_user else None)
        new_domain = _email_domain(new_user.username)
        if ref_domain and new_domain and ref_domain == new_domain:
            return "same_email_domain"

    if config_fraud.get("block_same_tenant_name", True):
        ref_name = _normalize_name(referrer_tenant.name if referrer_tenant else None)
        new_name = _normalize_name(new_tenant.name)
        if ref_name and new_name and ref_name == new_name:
            return "same_tenant_name"

    max_per_month = config_fraud.get("max_redemptions_per_month")
    try:
        max_per_month = int(max_per_month)
    except (TypeError, ValueError):
        max_per_month = None
    if max_per_month and recent_redemptions >= max_per_month:
        return "monthly_limit_reached"

    return None


def record_referral_redemption(
    db: Session,
    *,
    code: str,
    new_tenant: Tenant,
    new_user: User,
) -> ReferralRedemption | None:
    if not code:
        return None
    code = code.strip().lower()

    config = get_effective_program_config(db)
    if not config.is_enabled:
        return None

    invite = get_referral_invite_by_code(db, code=code)
    if not invite:
        return None

    if invite.status != "active":
        redemption = create_referral_redemption(
            db,
            invite_id=invite.id,
            new_tenant_id=new_tenant.id,
            status="rejected",
            reason="invite_inactive",
        )
        _log_referral_event(db, invite.tenant_id, f"referral.redemption.rejected:{redemption.reason}")
        return redemption

    now = utcnow()
    if invite.expires_at and invite.expires_at <= now:
        redemption = create_referral_redemption(
            db,
            invite_id=invite.id,
            new_tenant_id=new_tenant.id,
            status="rejected",
            reason="invite_expired",
        )
        _log_referral_event(db, invite.tenant_id, f"referral.redemption.rejected:{redemption.reason}")
        return redemption

    if invite.max_uses and invite.uses_count >= invite.max_uses:
        redemption = create_referral_redemption(
            db,
            invite_id=invite.id,
            new_tenant_id=new_tenant.id,
            status="rejected",
            reason="invite_maxed",
        )
        _log_referral_event(db, invite.tenant_id, f"referral.redemption.rejected:{redemption.reason}")
        return redemption

    existing = get_redemption_for_new_tenant(db, new_tenant_id=new_tenant.id)
    if existing:
        return existing

    referrer_user = None
    referrer_tenant = None
    try:
        referrer_tenant = db.query(Tenant).filter(Tenant.id == invite.tenant_id).first()
        if invite.created_by_user_id:
            referrer_user = db.query(User).filter(User.id == invite.created_by_user_id).first()
    except Exception:
        pass

    fraud_limits = config.fraud_limits_json or DEFAULT_FRAUD_LIMITS
    recent_redemptions = count_recent_redemptions(db, tenant_id=invite.tenant_id)
    reason = _fraud_block_reason(
        config_fraud=fraud_limits,
        referrer_user=referrer_user,
        new_user=new_user,
        referrer_tenant=referrer_tenant,
        new_tenant=new_tenant,
        recent_redemptions=recent_redemptions,
    )
    if reason:
        redemption = create_referral_redemption(
            db,
            invite_id=invite.id,
            new_tenant_id=new_tenant.id,
            status="rejected",
            reason=reason,
        )
        _log_referral_event(db, invite.tenant_id, f"referral.redemption.rejected:{reason}")
        return redemption

    redemption = create_referral_redemption(
        db,
        invite_id=invite.id,
        new_tenant_id=new_tenant.id,
        status="pending",
    )
    increment_invite_use(db, invite=invite)
    _log_referral_event(db, invite.tenant_id, "referral.redemption.pending")
    return redemption


def _eligible_for_reward(db: Session, *, tenant_id: int, eligibility_rules: dict) -> bool:
    paid_required = eligibility_rules.get("paid_plan_required", True)
    eligible_plans = eligibility_rules.get("eligible_plans")

    subscription = get_active_subscription_for_tenant(db, tenant_id)
    if not subscription:
        return False
    plan_key = (subscription.plan_key or "").lower() if subscription.plan_key else None
    if paid_required and plan_key == "free":
        return False
    if eligible_plans and plan_key and plan_key not in eligible_plans:
        return False
    return True


def _apply_stripe_coupon(*, customer_id: str, percent_off: int) -> str | None:
    if not settings.STRIPE_SECRET_KEY:
        return None
    try:
        import stripe

        stripe.api_key = settings.STRIPE_SECRET_KEY
        coupon = stripe.Coupon.create(percent_off=percent_off, duration="once")
        stripe.Customer.modify(customer_id, coupon=coupon.id)
        return coupon.id
    except Exception:
        return None


def process_referral_conversion(db: Session, *, new_tenant_id: int) -> ReferralRedemption | None:
    config = get_effective_program_config(db)
    if not config.is_enabled:
        return None
    if config.reward_type not in ALLOWED_REWARD_TYPES:
        return None

    redemption = (
        db.query(ReferralRedemption)
        .filter(
            ReferralRedemption.new_tenant_id == new_tenant_id,
            ReferralRedemption.status == "pending",
        )
        .first()
    )
    if not redemption:
        return None

    eligibility_rules = config.eligibility_rules_json or DEFAULT_ELIGIBILITY_RULES
    if not _eligible_for_reward(db, tenant_id=new_tenant_id, eligibility_rules=eligibility_rules):
        return None

    invite = db.query(ReferralInvite).filter(ReferralInvite.id == redemption.invite_id).first()
    if not invite:
        redemption.status = "rejected"
        redemption.reason = "invite_missing"
        db.commit()
        return redemption

    reward_value = float(config.reward_value or 0)
    reward_type = config.reward_type
    applied_at = None
    reason = None
    coupon_id = None

    if reward_type == "credit_gbp":
        create_credit_entry(
            db,
            tenant_id=invite.tenant_id,
            amount=reward_value,
            reason=f"referral:{redemption.id}",
        )
        applied_at = utcnow()
        redemption.status = "applied"
    else:
        subscription = get_active_subscription_for_tenant(db, invite.tenant_id)
        customer_id = subscription.stripe_customer_id if subscription else None
        percent_off = 100 if reward_type == "free_month" else int(reward_value or 0)
        if customer_id and percent_off > 0:
            coupon_id = _apply_stripe_coupon(customer_id=customer_id, percent_off=percent_off)
        if coupon_id:
            applied_at = utcnow()
            redemption.status = "applied"
        else:
            redemption.status = "approved"
            reason = "manual_reward_required"

    redemption.reward_applied_at = applied_at
    redemption.reason = reason
    redemption.stripe_coupon_id = coupon_id
    db.commit()
    db.refresh(redemption)
    if redemption.status == "applied":
        _log_referral_event(db, invite.tenant_id, "referral.reward.applied")
    elif redemption.status == "approved":
        _log_referral_event(db, invite.tenant_id, "referral.reward.approved")
    return redemption


def _log_referral_event(db: Session, tenant_id: int, event: str) -> None:
    try:
        from app.crud.audit import create_audit_log

        create_audit_log(db, tenant_id=tenant_id, username=None, event=event)
    except Exception:
        pass
