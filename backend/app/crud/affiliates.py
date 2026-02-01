from __future__ import annotations

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.affiliates import AffiliatePartner, AffiliateAttribution, AffiliateCommissionLedger


def create_partner(
    db: Session,
    *,
    name: str,
    code: str,
    status: str,
    commission_type: str,
    commission_value: float,
    payout_method: str = "manual",
) -> AffiliatePartner:
    partner = AffiliatePartner(
        name=name,
        code=code,
        status=status,
        commission_type=commission_type,
        commission_value=commission_value,
        payout_method=payout_method,
    )
    db.add(partner)
    db.commit()
    db.refresh(partner)
    return partner


def list_partners(db: Session) -> list[AffiliatePartner]:
    return db.query(AffiliatePartner).order_by(AffiliatePartner.created_at.desc()).all()


def get_partner_by_code(db: Session, *, code: str) -> AffiliatePartner | None:
    return db.query(AffiliatePartner).filter(AffiliatePartner.code == code).first()


def get_partner(db: Session, *, partner_id: int) -> AffiliatePartner | None:
    return db.query(AffiliatePartner).filter(AffiliatePartner.id == partner_id).first()


def update_partner(db: Session, *, partner: AffiliatePartner, updates: dict) -> AffiliatePartner:
    for key, value in updates.items():
        setattr(partner, key, value)
    db.commit()
    db.refresh(partner)
    return partner


def upsert_attribution(
    db: Session,
    *,
    partner_id: int,
    tenant_id: int,
    first_touch_at: datetime,
    last_touch_at: datetime,
    source_meta: dict | None,
) -> AffiliateAttribution:
    attribution = (
        db.query(AffiliateAttribution)
        .filter(AffiliateAttribution.tenant_id == tenant_id)
        .first()
    )
    if attribution:
        attribution.partner_id = partner_id
        attribution.last_touch_at = last_touch_at
        if source_meta:
            existing = attribution.source_meta_json if isinstance(attribution.source_meta_json, dict) else {}
            existing.update(source_meta)
            attribution.source_meta_json = existing
    else:
        attribution = AffiliateAttribution(
            partner_id=partner_id,
            tenant_id=tenant_id,
            first_touch_at=first_touch_at,
            last_touch_at=last_touch_at,
            source_meta_json=source_meta or {},
        )
        db.add(attribution)
    db.commit()
    db.refresh(attribution)
    return attribution


def get_attribution_for_tenant(db: Session, *, tenant_id: int) -> AffiliateAttribution | None:
    return db.query(AffiliateAttribution).filter(AffiliateAttribution.tenant_id == tenant_id).first()


def list_attributions_for_partner(db: Session, *, partner_id: int) -> list[AffiliateAttribution]:
    return (
        db.query(AffiliateAttribution)
        .filter(AffiliateAttribution.partner_id == partner_id)
        .order_by(AffiliateAttribution.created_at.desc())
        .all()
    )


def create_commission_entry(
    db: Session,
    *,
    partner_id: int,
    tenant_id: int,
    stripe_subscription_id: str | None,
    amount: float,
    currency: str,
    status: str,
    earned_at: datetime | None,
) -> AffiliateCommissionLedger:
    entry = AffiliateCommissionLedger(
        partner_id=partner_id,
        tenant_id=tenant_id,
        stripe_subscription_id=stripe_subscription_id,
        amount=amount,
        currency=currency,
        status=status,
        earned_at=earned_at,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def get_commission_for_subscription(
    db: Session,
    *,
    tenant_id: int,
    stripe_subscription_id: str | None,
) -> AffiliateCommissionLedger | None:
    if not stripe_subscription_id:
        return None
    return (
        db.query(AffiliateCommissionLedger)
        .filter(
            AffiliateCommissionLedger.tenant_id == tenant_id,
            AffiliateCommissionLedger.stripe_subscription_id == stripe_subscription_id,
        )
        .first()
    )


def list_commissions_for_partner(db: Session, *, partner_id: int) -> list[AffiliateCommissionLedger]:
    return (
        db.query(AffiliateCommissionLedger)
        .filter(AffiliateCommissionLedger.partner_id == partner_id)
        .order_by(AffiliateCommissionLedger.created_at.desc())
        .all()
    )


def list_commissions_for_tenant(db: Session, *, tenant_id: int) -> list[AffiliateCommissionLedger]:
    return (
        db.query(AffiliateCommissionLedger)
        .filter(AffiliateCommissionLedger.tenant_id == tenant_id)
        .order_by(AffiliateCommissionLedger.created_at.desc())
        .all()
    )


def sum_commissions(db: Session, *, partner_id: int, status: str) -> float:
    total = (
        db.query(func.coalesce(func.sum(AffiliateCommissionLedger.amount), 0))
        .filter(
            AffiliateCommissionLedger.partner_id == partner_id,
            AffiliateCommissionLedger.status == status,
        )
        .scalar()
    )
    try:
        return float(total or 0)
    except (TypeError, ValueError):
        return 0.0
