from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from app.core.db import Base
from app.core.time import utcnow
from app.models.mixins import TimestampMixin


JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class TenantSCIMConfig(TimestampMixin, Base):
    __tablename__ = "tenant_scim_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_tenant_scim_config_tenant"),
        Index("ix_tenant_scim_config_tenant_enabled", "tenant_id", "is_enabled"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
    is_enabled = Column(Boolean, nullable=False, default=False)
    scim_token_hash = Column(String, nullable=True)
    token_last_rotated_at = Column(DateTime, nullable=True, default=utcnow)
    default_role = Column(String, nullable=False, default="viewer")
    group_role_mappings_json = Column(JSON_TYPE, nullable=True)
