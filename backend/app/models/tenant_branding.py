from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Boolean, Index
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.models.mixins import TimestampMixin


class TenantBranding(TimestampMixin, Base):
    __tablename__ = "tenant_branding"
    __table_args__ = (
        Index("ix_tenant_branding_custom_domain", "custom_domain"),
    )

    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    is_enabled = Column(Boolean, nullable=False, default=False)
    brand_name = Column(String, nullable=True)
    logo_url = Column(String, nullable=True)
    primary_color = Column(String, nullable=True)
    accent_color = Column(String, nullable=True)
    custom_domain = Column(String, nullable=True)
    domain_verification_token = Column(String, nullable=True)
    domain_verified_at = Column(DateTime, nullable=True)
    badge_branding_mode = Column(String, nullable=False, default="your_brand")

    tenant = relationship("Tenant", back_populates="branding", lazy="selectin")
