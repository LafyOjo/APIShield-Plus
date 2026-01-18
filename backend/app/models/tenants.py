from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.models.mixins import TimestampMixin


class Tenant(TimestampMixin, Base):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False, index=True)
    deleted_at = Column(DateTime, nullable=True)
    created_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    memberships = relationship("Membership", back_populates="tenant", lazy="selectin")
    websites = relationship("Website", back_populates="tenant", lazy="selectin")
    subscriptions = relationship("Subscription", back_populates="tenant", lazy="selectin")
    api_keys = relationship("APIKey", back_populates="tenant", lazy="selectin")
    invites = relationship("Invite", back_populates="tenant", lazy="selectin")
    created_by = relationship(
        "User",
        back_populates="created_tenants",
        foreign_keys=[created_by_user_id],
        lazy="selectin",
    )
    settings = relationship(
        "TenantSettings",
        back_populates="tenant",
        uselist=False,
        lazy="selectin",
    )
    usage_periods = relationship("TenantUsage", back_populates="tenant", lazy="selectin")
    retention_policies = relationship(
        "DataRetentionPolicy",
        back_populates="tenant",
        lazy="selectin",
    )
    feature_entitlements = relationship(
        "FeatureEntitlement",
        back_populates="tenant",
        lazy="selectin",
    )
    domain_verifications = relationship(
        "DomainVerification",
        back_populates="tenant",
        lazy="selectin",
    )
    project_tags = relationship(
        "ProjectTag",
        back_populates="tenant",
        lazy="selectin",
    )
    external_integrations = relationship(
        "ExternalIntegration",
        back_populates="tenant",
        lazy="selectin",
    )
