from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from app.core.db import Base
from app.models.mixins import TimestampMixin


JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class MarketplaceTemplate(TimestampMixin, Base):
    __tablename__ = "marketplace_templates"
    __table_args__ = (
        Index("ix_marketplace_templates_type", "template_type"),
        Index("ix_marketplace_templates_status", "status"),
        Index("ix_marketplace_templates_source", "source"),
        Index("ix_marketplace_templates_stack", "stack_type"),
    )

    id = Column(Integer, primary_key=True, index=True)
    template_type = Column(String, nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    stack_type = Column(String, nullable=True)
    tags = Column(JSON_TYPE, nullable=True)
    content_json = Column(JSON_TYPE, nullable=False)
    author_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    source = Column(String, nullable=False, default="community")
    status = Column(String, nullable=False, default="draft")
    safety_notes = Column(Text, nullable=True)
    downloads_count = Column(Integer, nullable=False, default=0)


class TemplateImportEvent(TimestampMixin, Base):
    __tablename__ = "template_import_events"
    __table_args__ = (
        Index("ix_template_import_events_tenant", "tenant_id"),
        Index("ix_template_import_events_template", "template_id"),
        Index("ix_template_import_events_imported", "imported_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
    template_id = Column(Integer, ForeignKey("marketplace_templates.id", ondelete="CASCADE"), nullable=False)
    imported_at = Column(DateTime, nullable=False)
    applied_to_incident_id = Column(Integer, ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True)
