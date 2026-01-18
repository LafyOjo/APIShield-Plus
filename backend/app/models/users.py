from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.core.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="user")
    policy_id = Column(Integer, ForeignKey("policies.id"), nullable=True)

    memberships = relationship(
        "Membership",
        back_populates="user",
        lazy="selectin",
        foreign_keys="Membership.user_id",
    )
    created_tenants = relationship(
        "Tenant",
        back_populates="created_by",
        foreign_keys="Tenant.created_by_user_id",
        lazy="selectin",
    )
    created_websites = relationship(
        "Website",
        back_populates="created_by",
        foreign_keys="Website.created_by_user_id",
        lazy="selectin",
    )
    created_api_keys = relationship(
        "APIKey",
        back_populates="created_by",
        foreign_keys="APIKey.created_by_user_id",
        lazy="selectin",
    )
    revoked_api_keys = relationship(
        "APIKey",
        back_populates="revoked_by",
        foreign_keys="APIKey.revoked_by_user_id",
        lazy="selectin",
    )
    created_invites = relationship(
        "Invite",
        back_populates="created_by",
        foreign_keys="Invite.created_by_user_id",
        lazy="selectin",
    )
    created_memberships = relationship(
        "Membership",
        back_populates="created_by",
        foreign_keys="Membership.created_by_user_id",
        lazy="selectin",
    )
    created_domain_verifications = relationship(
        "DomainVerification",
        back_populates="created_by",
        foreign_keys="DomainVerification.created_by_user_id",
        lazy="selectin",
    )
    updated_feature_entitlements = relationship(
        "FeatureEntitlement",
        back_populates="updated_by",
        foreign_keys="FeatureEntitlement.updated_by_user_id",
        lazy="selectin",
    )
    profile = relationship(
        "UserProfile",
        back_populates="user",
        uselist=False,
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    @property
    def display_name(self):
        profile = getattr(self, "profile", None)
        return profile.display_name if profile else None
