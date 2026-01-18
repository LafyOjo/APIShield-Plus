from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.models.mixins import TimestampMixin


class APIKey(TimestampMixin, Base):
    __tablename__ = "api_keys"
    __table_args__ = (
        Index("ix_api_keys_tenant_id", "tenant_id"),
        Index("ix_api_keys_tenant_environment", "tenant_id", "environment_id"),
        Index("ix_api_keys_tenant_created_at", "tenant_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False)
    website_id = Column(Integer, ForeignKey("websites.id", ondelete="RESTRICT"), nullable=False)
    environment_id = Column(
        Integer,
        ForeignKey("website_environments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    public_key = Column(String, nullable=False, unique=True, index=True)
    secret_hash = Column(String, nullable=False)
    name = Column(String, nullable=True)
    status = Column(String, nullable=False, default="active")
    created_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_used_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    revoked_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    tenant = relationship("Tenant", back_populates="api_keys", lazy="selectin")
    website = relationship("Website", back_populates="api_keys", lazy="selectin")
    environment = relationship("WebsiteEnvironment", back_populates="api_keys", lazy="selectin")
    created_by = relationship(
        "User",
        back_populates="created_api_keys",
        foreign_keys=[created_by_user_id],
        lazy="selectin",
    )
    revoked_by = relationship(
        "User",
        back_populates="revoked_api_keys",
        foreign_keys=[revoked_by_user_id],
        lazy="selectin",
    )
