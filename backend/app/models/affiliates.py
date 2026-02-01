from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.core.db import Base
from app.models.mixins import TimestampMixin


JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class AffiliatePartner(TimestampMixin, Base):
    __tablename__ = "affiliate_partners"
    __table_args__ = (
        UniqueConstraint("code", name="uq_affiliate_partners_code"),
        Index("ix_affiliate_partners_status", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="active")
    code = Column(String, nullable=False)
    commission_type = Column(String, nullable=False, default="percent")
    commission_value = Column(Numeric(10, 2), nullable=False, default=0)
    payout_method = Column(String, nullable=False, default="manual")


class AffiliateAttribution(TimestampMixin, Base):
    __tablename__ = "affiliate_attributions"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_affiliate_attributions_tenant"),
        Index("ix_affiliate_attributions_partner", "partner_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    partner_id = Column(Integer, ForeignKey("affiliate_partners.id", ondelete="RESTRICT"), nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
    first_touch_at = Column(DateTime, nullable=False)
    last_touch_at = Column(DateTime, nullable=False)
    source_meta_json = Column(JSON_TYPE, nullable=True)


class AffiliateCommissionLedger(TimestampMixin, Base):
    __tablename__ = "affiliate_commission_ledger"
    __table_args__ = (
        UniqueConstraint(
            "partner_id",
            "tenant_id",
            "stripe_subscription_id",
            name="uq_affiliate_commission_unique",
        ),
        Index("ix_affiliate_commission_partner", "partner_id"),
        Index("ix_affiliate_commission_status", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    partner_id = Column(Integer, ForeignKey("affiliate_partners.id", ondelete="RESTRICT"), nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
    stripe_subscription_id = Column(String, nullable=True)
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String, nullable=False, default="GBP")
    status = Column(String, nullable=False, default="pending")
    earned_at = Column(DateTime, nullable=True)
    paid_at = Column(DateTime, nullable=True)
    void_reason = Column(Text, nullable=True)
