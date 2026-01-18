from sqlalchemy import Column, ForeignKey, Integer, String, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.models.mixins import TimestampMixin


JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class TenantSettings(TimestampMixin, Base):
    __tablename__ = "tenant_settings"

    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    timezone = Column(String, nullable=False, default="UTC")
    retention_days = Column(Integer, nullable=False, default=7)
    alert_prefs = Column(JSON_TYPE, nullable=False, default=dict)

    tenant = relationship("Tenant", back_populates="settings", lazy="selectin")
