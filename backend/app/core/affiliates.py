from __future__ import annotations

import secrets
from datetime import timedelta

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.config import settings
from app.core.time import utcnow
from app.crud.affiliates import (
    create_commission_entry,
    get_attribution_for_tenant,
    get_commission_for_subscription,
    get_partner_by_code,
    sum_commissions,
    upsert_attribution,
)
from app.crud.plans import get_plan_by_name
from app.crud.subscriptions import get_active_subscription_for_tenant
from app.models.affiliates import AffiliateCommissionLedger, AffiliatePartner, AffiliateAttribution
from app.models.plans import Plan


ALLOWED_COMMISSION_TYPES = {"percent", "flat"}


def generate_affiliate_code() -> str:
    token = secrets.token_urlsafe(6).replace("-", "").replace("_", "")
    return f"aff_{token.lower()}"


def build_affiliate_link(code: str) -> str:
    base = settings.APP_BASE_URL or settings.FRONTEND_BASE_URL or "http://localhost:3000"
    return f"{base.rstrip('/')}/signup?aff={code}"


def record_affiliate_attribution(
    db: Session,
    *,
    affiliate_code: str,
    tenant_id: int,
    source_meta: dict | None = None,
) -> bool:
    if not affiliate_code:
        return False
    affiliate_code = affiliate_code.strip().lower()
    partner = get_partner_by_code(db, code=affiliate_code)
    if not partner or partner.status != "active":
        return False

    now = utcnow()
    upsert_attribution(
        db,
        partner_id=partner.id,
        tenant_id=tenant_id,
        first_touch_at=now,
        last_touch_at=now,
        source_meta=source_meta or {},
    )
    return True


def _plan_amount(plan: Plan | None) -> float:
    if not plan:
        return 0.0
    try:
        return float(plan.price_monthly or 0)
    except (TypeError, ValueError):
        return 0.0


def _resolve_plan_for_subscription(db: Session, tenant_id: int) -> Plan | None:
    subscription = get_active_subscription_for_tenant(db, tenant_id)
    if not subscription:
        return None
    if subscription.plan is not None:
        return subscription.plan
    if subscription.plan_id:
        return db.query(Plan).filter(Plan.id == subscription.plan_id).first()
    if subscription.plan_key:
        plan_name = subscription.plan_key.title()
        return get_plan_by_name(db, plan_name)
    return None


def create_affiliate_commission(
    db: Session,
    *,
    tenant_id: int,
    stripe_subscription_id: str | None,
    plan_amount: float,
) -> AffiliateCommissionLedger | None:
    if not stripe_subscription_id:
        return None
    attribution = get_attribution_for_tenant(db, tenant_id=tenant_id)
    if not attribution:
        return None
    partner = db.query(AffiliatePartner).filter(AffiliatePartner.id == attribution.partner_id).first()

    if not partner or partner.status != "active":
        return None

    if stripe_subscription_id and get_commission_for_subscription(
        db,
        tenant_id=tenant_id,
        stripe_subscription_id=stripe_subscription_id,
    ):
        return None

    commission_type = partner.commission_type
    if commission_type not in ALLOWED_COMMISSION_TYPES:
        return None

    commission_value = float(partner.commission_value or 0)
    if commission_type == "percent":
        amount = plan_amount * (commission_value / 100.0)
    else:
        amount = commission_value

    if amount <= 0:
        return None

    refund_days = int(getattr(settings, "AFFILIATE_REFUND_WINDOW_DAYS", 14))
    earned_at = utcnow() + timedelta(days=refund_days)

    return create_commission_entry(
        db,
        partner_id=partner.id,
        tenant_id=tenant_id,
        stripe_subscription_id=stripe_subscription_id,
        amount=amount,
        currency="GBP",
        status="pending",
        earned_at=earned_at,
    )


def process_affiliate_conversion(
    db: Session,
    *,
    tenant_id: int,
    stripe_subscription_id: str | None,
) -> AffiliateCommissionLedger | None:
    plan = _resolve_plan_for_subscription(db, tenant_id)
    amount = _plan_amount(plan)
    return create_affiliate_commission(
        db,
        tenant_id=tenant_id,
        stripe_subscription_id=stripe_subscription_id,
        plan_amount=amount,
    )


def void_affiliate_commission(
    db: Session,
    *,
    tenant_id: int,
    stripe_subscription_id: str | None,
    reason: str,
) -> AffiliateCommissionLedger | None:
    if not stripe_subscription_id:
        return None
    ledger = get_commission_for_subscription(
        db,
        tenant_id=tenant_id,
        stripe_subscription_id=stripe_subscription_id,
    )
    if not ledger:
        return None
    if ledger.status in {"paid", "void"}:
        return ledger
    ledger.status = "void"
    ledger.void_reason = reason
    ledger.paid_at = None
    db.commit()
    db.refresh(ledger)
    return ledger


def build_partner_summary(db: Session, *, partner_id: int) -> dict:
    signups = (
        db.query(func.count())
        .select_from(AffiliateAttribution)
        .filter(AffiliateAttribution.partner_id == partner_id)
        .scalar()
        or 0
    )
    conversions = (
        db.query(func.count())
        .select_from(AffiliateCommissionLedger)
        .filter(
            AffiliateCommissionLedger.partner_id == partner_id,
            AffiliateCommissionLedger.status.in_(["pending", "earned", "paid"]),
        )
        .scalar()
        or 0
    )
    return {
        "signups": int(signups),
        "conversions": int(conversions),
        "commission_pending": sum_commissions(db, partner_id=partner_id, status="pending"),
        "commission_earned": sum_commissions(db, partner_id=partner_id, status="earned"),
        "commission_paid": sum_commissions(db, partner_id=partner_id, status="paid"),
    }
