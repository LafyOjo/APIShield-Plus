from sqlalchemy import Boolean, Column, Float, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.dialects.postgresql import JSONB

from app.core.db import Base
from app.models.mixins import TimestampMixin


JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class WebsiteStackProfile(TimestampMixin, Base):
    __tablename__ = "website_stack_profiles"
    __table_args__ = (
        Index("ix_stack_profiles_tenant_website", "tenant_id", "website_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
    website_id = Column(Integer, ForeignKey("websites.id", ondelete="RESTRICT"), nullable=False, unique=True, index=True)
    stack_type = Column(String, nullable=False, default="custom")
    confidence = Column(Float, nullable=False, default=0.2)
    detected_signals_json = Column(JSON_TYPE, nullable=True)
    manual_override = Column(Boolean, nullable=False, default=False)
