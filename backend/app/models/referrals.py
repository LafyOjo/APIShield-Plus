from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    JSON,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.core.db import Base
from app.core.time import utcnow
from app.models.mixins import TimestampMixin


JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class ReferralProgramConfig(TimestampMixin, Base):
    __tablename__ = "referral_program_config"

    id = Column(Integer, primary_key=True, index=True)
    is_enabled = Column(Boolean, nullable=False, default=True)
    reward_type = Column(String, nullable=False, default="credit_gbp")
    reward_value = Column(Numeric(10, 2), nullable=False, default=0)
    eligibility_rules_json = Column(JSON_TYPE, nullable=False, default=dict)
    fraud_limits_json = Column(JSON_TYPE, nullable=False, default=dict)


class ReferralInvite(TimestampMixin, Base):
    __tablename__ = "referral_invites"
    __table_args__ = (
        UniqueConstraint("code", name="uq_referral_invites_code"),
        Index("ix_referral_invites_tenant_status", "tenant_id", "status"),
        Index("ix_referral_invites_expires", "expires_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    code = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    max_uses = Column(Integer, nullable=False, default=20)
    uses_count = Column(Integer, nullable=False, default=0)
    status = Column(String, nullable=False, default="active")


class ReferralRedemption(TimestampMixin, Base):
    __tablename__ = "referral_redemptions"
    __table_args__ = (
        UniqueConstraint("new_tenant_id", name="uq_referral_redemptions_new_tenant"),
        Index("ix_referral_redemptions_invite", "invite_id"),
        Index("ix_referral_redemptions_status", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    invite_id = Column(Integer, ForeignKey("referral_invites.id", ondelete="RESTRICT"), nullable=False)
    new_tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
    redeemed_at = Column(DateTime, nullable=False, default=utcnow)
    status = Column(String, nullable=False, default="pending")
    reason = Column(Text, nullable=True)
    reward_applied_at = Column(DateTime, nullable=True)
    stripe_coupon_id = Column(String, nullable=True)


class CreditLedger(TimestampMixin, Base):
    __tablename__ = "credit_ledger"
    __table_args__ = (
        Index("ix_credit_ledger_tenant_created", "tenant_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String, nullable=False, default="GBP")
    reason = Column(String, nullable=True)
    applied_to_invoice_id = Column(String, nullable=True)
