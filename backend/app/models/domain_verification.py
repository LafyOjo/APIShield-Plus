from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.models.mixins import TimestampMixin


class DomainVerification(TimestampMixin, Base):
    __tablename__ = "domain_verifications"
    __table_args__ = (
        Index("ix_domain_verifications_tenant_website", "tenant_id", "website_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    website_id = Column(
        Integer,
        ForeignKey("websites.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    method = Column(String, nullable=False)
    token = Column(String, nullable=False, unique=True, index=True)
    status = Column(String, nullable=False, default="pending")
    created_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    verified_at = Column(DateTime, nullable=True)
    last_checked_at = Column(DateTime, nullable=True)

    tenant = relationship("Tenant", back_populates="domain_verifications", lazy="selectin")
    website = relationship("Website", back_populates="domain_verifications", lazy="selectin")
    created_by = relationship(
        "User",
        back_populates="created_domain_verifications",
        foreign_keys=[created_by_user_id],
        lazy="selectin",
    )
