from sqlalchemy import Column, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, Boolean
from sqlalchemy.dialects.postgresql import JSONB

from app.core.db import Base
from app.models.mixins import TimestampMixin


JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class ProtectionPreset(TimestampMixin, Base):
    __tablename__ = "protection_presets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "incident_id", "preset_type", name="uq_preset_incident_type"),
        Index("ix_presets_tenant_incident", "tenant_id", "incident_id"),
        Index("ix_presets_tenant_created", "tenant_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
    website_id = Column(Integer, ForeignKey("websites.id", ondelete="RESTRICT"), nullable=True, index=True)
    incident_id = Column(Integer, ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True)
    preset_type = Column(String, nullable=False)
    content_json = Column(JSON_TYPE, nullable=False)
    is_demo = Column(Boolean, nullable=False, default=False)
