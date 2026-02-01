from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from app.core.db import Base
from app.models.mixins import TimestampMixin


JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class PartnerUser(TimestampMixin, Base):
    __tablename__ = "partner_users"
    __table_args__ = (
        UniqueConstraint("partner_id", "user_id", name="uq_partner_users_partner_user"),
        Index("ix_partner_users_partner", "partner_id"),
        Index("ix_partner_users_user", "user_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    partner_id = Column(Integer, ForeignKey("affiliate_partners.id", ondelete="RESTRICT"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    role = Column(String, nullable=False, default="viewer")


class PartnerLead(TimestampMixin, Base):
    __tablename__ = "partner_leads"
    __table_args__ = (
        UniqueConstraint("lead_id", name="uq_partner_leads_lead_id"),
        Index("ix_partner_leads_partner", "partner_id"),
        Index("ix_partner_leads_status", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    partner_id = Column(Integer, ForeignKey("affiliate_partners.id", ondelete="RESTRICT"), nullable=False)
    lead_id = Column(String, nullable=False)
    status = Column(String, nullable=False, default="new")
    source_meta_json = Column(JSON_TYPE, nullable=True)
    associated_tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True)
