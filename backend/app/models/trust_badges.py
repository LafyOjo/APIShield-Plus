from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint

from app.core.db import Base
from app.models.mixins import TimestampMixin


class TrustBadgeConfig(TimestampMixin, Base):
    __tablename__ = "trust_badge_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "website_id", name="uq_trust_badge_tenant_website"),
        Index("ix_trust_badge_website", "website_id"),
        Index("ix_trust_badge_tenant", "tenant_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
    website_id = Column(Integer, ForeignKey("websites.id", ondelete="RESTRICT"), nullable=False, index=True)
    is_enabled = Column(Boolean, nullable=False, default=False)
    style = Column(String, nullable=False, default="light")
    show_score = Column(Boolean, nullable=False, default=True)
    show_branding = Column(Boolean, nullable=False, default=True)
    clickthrough_url = Column(String, nullable=True)
    badge_key_enc = Column(String, nullable=False)
