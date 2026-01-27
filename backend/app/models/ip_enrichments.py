from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Index,
    Float,
)

from app.core.db import Base


class IPEnrichment(Base):
    __tablename__ = "ip_enrichments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "ip_hash", name="uq_ip_enrichments_tenant_ip_hash"),
        Index("ix_ip_enrichments_tenant_last_seen", "tenant_id", "last_seen_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
    ip_hash = Column(String, nullable=False, index=True)
    first_seen_at = Column(DateTime, nullable=False)
    last_seen_at = Column(DateTime, nullable=False)
    country_code = Column(String, nullable=True)
    region = Column(String, nullable=True)
    city = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    asn_number = Column(Integer, nullable=True)
    asn_org = Column(String, nullable=True)
    is_datacenter = Column(Boolean, nullable=True)
    source = Column(String, nullable=True)
    last_lookup_at = Column(DateTime, nullable=True)
    lookup_status = Column(String, nullable=False, default="pending")
    failure_reason = Column(String, nullable=True)
    is_demo = Column(Boolean, nullable=False, default=False)
