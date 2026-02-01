from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.referrals import (
    ReferralProgramConfig,
    ReferralInvite,
    ReferralRedemption,
    CreditLedger,
)


DEFAULT_ELIGIBILITY_RULES = {"paid_plan_required": True}
DEFAULT_FRAUD_LIMITS = {
    "max_redemptions_per_month": 5,
    "block_same_email_domain": True,
    "block_same_tenant_name": True,
}


def get_program_config(db: Session) -> ReferralProgramConfig | None:
    return db.query(ReferralProgramConfig).order_by(ReferralProgramConfig.id.asc()).first()


def upsert_program_config(db: Session, *, payload: dict) -> ReferralProgramConfig:
    config = get_program_config(db)
    if not config:
        config = ReferralProgramConfig(**payload)
        db.add(config)
    else:
        for key, value in payload.items():
            setattr(config, key, value)
    db.commit()
    db.refresh(config)
    return config


def get_effective_program_config(db: Session) -> ReferralProgramConfig:
    config = get_program_config(db)
    if not config:
        config = ReferralProgramConfig(
            is_enabled=True,
            reward_type="credit_gbp",
            reward_value=50,
            eligibility_rules_json=DEFAULT_ELIGIBILITY_RULES,
            fraud_limits_json=DEFAULT_FRAUD_LIMITS,
        )
        db.add(config)
        db.commit()
        db.refresh(config)
    updated = False
    if not config.eligibility_rules_json:
        config.eligibility_rules_json = dict(DEFAULT_ELIGIBILITY_RULES)
        updated = True
    if not config.fraud_limits_json:
        config.fraud_limits_json = dict(DEFAULT_FRAUD_LIMITS)
        updated = True
    if updated:
        db.commit()
    return config


def create_referral_invite(
    db: Session,
    *,
    tenant_id: int,
    created_by_user_id: int | None,
    code: str,
    expires_at: datetime | None,
    max_uses: int,
) -> ReferralInvite:
    invite = ReferralInvite(
        tenant_id=tenant_id,
        created_by_user_id=created_by_user_id,
        code=code,
        expires_at=expires_at,
        max_uses=max_uses,
        uses_count=0,
        status="active",
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return invite


def list_referral_invites(db: Session, *, tenant_id: int) -> list[ReferralInvite]:
    return (
        db.query(ReferralInvite)
        .filter(ReferralInvite.tenant_id == tenant_id)
        .order_by(ReferralInvite.created_at.desc())
        .all()
    )


def get_referral_invite_by_code(db: Session, *, code: str) -> ReferralInvite | None:
    return (
        db.query(ReferralInvite)
        .filter(ReferralInvite.code == code)
        .first()
    )


def get_referral_invite(db: Session, *, invite_id: int) -> ReferralInvite | None:
    return db.query(ReferralInvite).filter(ReferralInvite.id == invite_id).first()


def increment_invite_use(db: Session, *, invite: ReferralInvite) -> None:
    invite.uses_count = int(invite.uses_count or 0) + 1
    db.commit()


def create_referral_redemption(
    db: Session,
    *,
    invite_id: int,
    new_tenant_id: int,
    status: str,
    reason: str | None = None,
) -> ReferralRedemption:
    redemption = ReferralRedemption(
        invite_id=invite_id,
        new_tenant_id=new_tenant_id,
        status=status,
        reason=reason,
    )
    db.add(redemption)
    db.commit()
    db.refresh(redemption)
    return redemption


def get_redemption_for_new_tenant(db: Session, *, new_tenant_id: int) -> ReferralRedemption | None:
    return (
        db.query(ReferralRedemption)
        .filter(ReferralRedemption.new_tenant_id == new_tenant_id)
        .first()
    )


def list_redemptions_for_tenant(db: Session, *, tenant_id: int) -> list[ReferralRedemption]:
    return (
        db.query(ReferralRedemption)
        .join(ReferralInvite, ReferralRedemption.invite_id == ReferralInvite.id)
        .filter(ReferralInvite.tenant_id == tenant_id)
        .order_by(ReferralRedemption.redeemed_at.desc())
        .all()
    )


def count_recent_redemptions(db: Session, *, tenant_id: int, window_days: int = 30) -> int:
    cutoff = datetime.utcnow() - timedelta(days=window_days)
    return (
        db.query(func.count(ReferralRedemption.id))
        .join(ReferralInvite, ReferralRedemption.invite_id == ReferralInvite.id)
        .filter(
            ReferralInvite.tenant_id == tenant_id,
            ReferralRedemption.redeemed_at >= cutoff,
            ReferralRedemption.status != "rejected",
        )
        .scalar()
        or 0
    )


def create_credit_entry(
    db: Session,
    *,
    tenant_id: int,
    amount: float,
    reason: str,
    currency: str = "GBP",
) -> CreditLedger:
    entry = CreditLedger(
        tenant_id=tenant_id,
        amount=amount,
        currency=currency,
        reason=reason,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def get_credit_balance(db: Session, *, tenant_id: int) -> float:
    total = (
        db.query(func.coalesce(func.sum(CreditLedger.amount), 0))
        .filter(CreditLedger.tenant_id == tenant_id)
        .scalar()
    )
    try:
        return float(total or 0)
    except (TypeError, ValueError):
        return 0.0
