from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, JSON, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.models.mixins import TimestampMixin

JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class Tenant(TimestampMixin, Base):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False, index=True)
    data_region = Column(String, nullable=False, default="us")
    created_region = Column(String, nullable=False, default="us")
    allowed_regions = Column(JSON_TYPE, nullable=True)
    is_demo_mode = Column(Boolean, nullable=False, default=False)
    demo_seeded_at = Column(DateTime, nullable=True)
    demo_expires_at = Column(DateTime, nullable=True)
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
    branding = relationship(
        "TenantBranding",
        back_populates="tenant",
        uselist=False,
        lazy="selectin",
    )
    onboarding_state = relationship(
        "OnboardingState",
        back_populates="tenant",
        uselist=False,
        lazy="selectin",
    )
    activation_metric = relationship(
        "ActivationMetric",
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
    dataset_retention_policies = relationship(
        "TenantRetentionPolicy",
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
    notification_channels = relationship(
        "NotificationChannel",
        back_populates="tenant",
        lazy="selectin",
    )
    notification_rules = relationship(
        "NotificationRule",
        lazy="selectin",
    )
    sso_config = relationship(
        "TenantSSOConfig",
        back_populates="tenant",
        uselist=False,
        lazy="selectin",
    )
    behaviour_events = relationship(
        "BehaviourEvent",
        back_populates="tenant",
        lazy="noload",
    )
    behaviour_sessions = relationship(
        "BehaviourSession",
        back_populates="tenant",
        lazy="noload",
    )
    queued_jobs = relationship(
        "JobQueue",
        back_populates="tenant",
        lazy="noload",
    )
    dead_letter_jobs = relationship(
        "JobDeadLetter",
        back_populates="tenant",
        lazy="noload",
    )
