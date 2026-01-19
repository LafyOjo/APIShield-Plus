from sqlalchemy import Column, DateTime, Enum, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.models.enums import WebsiteStatusEnum
from app.models.mixins import TimestampMixin


class Website(TimestampMixin, Base):
    __tablename__ = "websites"
    __table_args__ = (
        UniqueConstraint("tenant_id", "domain", name="uq_websites_tenant_domain"),
        Index("ix_websites_tenant_id", "tenant_id"),
        Index("ix_websites_tenant_created_at", "tenant_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False)
    domain = Column(String, nullable=False)
    display_name = Column(String, nullable=True)
    status = Column(
        Enum(
            WebsiteStatusEnum,
            name="website_status_enum",
            native_enum=False,
            validate_strings=True,
        ),
        nullable=False,
        default=WebsiteStatusEnum.ACTIVE,
    )
    deleted_at = Column(DateTime, nullable=True)
    created_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    tenant = relationship("Tenant", back_populates="websites", lazy="selectin")
    environments = relationship("WebsiteEnvironment", back_populates="website", lazy="selectin")
    api_keys = relationship("APIKey", back_populates="website", lazy="selectin")
    domain_verifications = relationship(
        "DomainVerification",
        back_populates="website",
        lazy="selectin",
    )
    tags = relationship(
        "ProjectTag",
        secondary="website_tags",
        back_populates="websites",
        lazy="selectin",
        passive_deletes=True,
    )
    created_by = relationship(
        "User",
        back_populates="created_websites",
        foreign_keys=[created_by_user_id],
        lazy="selectin",
    )
    behaviour_events = relationship(
        "BehaviourEvent",
        back_populates="website",
        lazy="noload",
    )
    behaviour_sessions = relationship(
        "BehaviourSession",
        back_populates="website",
        lazy="noload",
    )
