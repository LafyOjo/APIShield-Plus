from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import JSON

from app.core.db import Base
from app.models.mixins import TimestampMixin


JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class IntegrationListing(TimestampMixin, Base):
    __tablename__ = "integration_listings"
    __table_args__ = (
        Index("ix_integration_listings_key", "key", unique=True),
        Index("ix_integration_listings_category", "category"),
        Index("ix_integration_listings_featured", "is_featured"),
    )

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, nullable=False, unique=True)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    docs_url = Column(String, nullable=True)
    install_type = Column(String, nullable=False)
    is_featured = Column(Boolean, nullable=False, default=False)
    plan_required = Column(String, nullable=True)
    install_url = Column(String, nullable=True)
    copy_payload = Column(Text, nullable=True)
    stack_types = Column(JSON_TYPE, nullable=True)


class IntegrationInstallEvent(TimestampMixin, Base):
    __tablename__ = "integration_install_events"
    __table_args__ = (
        Index("ix_integration_installs_tenant", "tenant_id"),
        Index("ix_integration_installs_key", "integration_key"),
        Index("ix_integration_installs_installed", "installed_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
    website_id = Column(Integer, ForeignKey("websites.id", ondelete="RESTRICT"), nullable=True, index=True)
    integration_key = Column(String, nullable=False)
    installed_at = Column(DateTime, nullable=False)
    method = Column(String, nullable=False)
    metadata_json = Column(JSON_TYPE, nullable=True)
