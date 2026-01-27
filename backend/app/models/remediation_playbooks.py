from sqlalchemy import Column, ForeignKey, Index, Integer, JSON, String, Boolean
from sqlalchemy.dialects.postgresql import JSONB

from app.core.db import Base
from app.models.mixins import TimestampMixin


JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class RemediationPlaybook(TimestampMixin, Base):
    __tablename__ = "remediation_playbooks"
    __table_args__ = (
        Index("ix_playbooks_tenant_incident", "tenant_id", "incident_id"),
        Index("ix_playbooks_tenant_created", "tenant_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
    website_id = Column(Integer, ForeignKey("websites.id", ondelete="RESTRICT"), nullable=True, index=True)
    environment_id = Column(
        Integer,
        ForeignKey("website_environments.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    incident_id = Column(Integer, ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True)
    stack_type = Column(String, nullable=False, default="custom")
    status = Column(String, nullable=False, default="draft")
    version = Column(Integer, nullable=False, default=1)
    sections_json = Column(JSON_TYPE, nullable=False)
    is_demo = Column(Boolean, nullable=False, default=False)
