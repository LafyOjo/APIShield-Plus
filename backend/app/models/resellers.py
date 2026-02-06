from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.core.db import Base
from app.models.mixins import TimestampMixin


JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class ResellerAccount(TimestampMixin, Base):
    __tablename__ = "reseller_accounts"
    __table_args__ = (
        UniqueConstraint("partner_id", name="uq_reseller_accounts_partner"),
    )

    id = Column(Integer, primary_key=True, index=True)
    partner_id = Column(Integer, ForeignKey("affiliate_partners.id", ondelete="RESTRICT"), nullable=False)
    is_enabled = Column(Boolean, nullable=False, default=True)
    billing_mode = Column(String, nullable=False, default="customer_pays_stripe")
    allowed_plans = Column(JSON_TYPE, nullable=True)


class ManagedTenant(TimestampMixin, Base):
    __tablename__ = "managed_tenants"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_managed_tenants_tenant"),
        Index("ix_managed_tenants_partner", "reseller_partner_id"),
        Index("ix_managed_tenants_status", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    reseller_partner_id = Column(
        Integer,
        ForeignKey("affiliate_partners.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False)
    status = Column(String, nullable=False, default="active")
