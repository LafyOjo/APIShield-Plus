from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, JSON, Float, Boolean
from sqlalchemy.dialects.postgresql import JSONB

from app.core.db import Base


JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class TrustSnapshot(Base):
    __tablename__ = "trust_snapshots"
    __table_args__ = (
        Index("ix_trust_snapshots_tenant_website_bucket", "tenant_id", "website_id", "bucket_start"),
        Index(
            "ix_trust_snapshots_tenant_website_path_bucket",
            "tenant_id",
            "website_id",
            "path",
            "bucket_start",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
    website_id = Column(Integer, ForeignKey("websites.id", ondelete="RESTRICT"), nullable=False, index=True)
    environment_id = Column(
        Integer,
        ForeignKey("website_environments.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    bucket_start = Column(DateTime, nullable=False, index=True)
    path = Column(String, nullable=True)
    trust_score = Column(Integer, nullable=False)
    confidence = Column(Float, nullable=False)
    factor_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    is_demo = Column(Boolean, nullable=False, default=False)


class TrustFactorAgg(Base):
    __tablename__ = "trust_factor_aggs"
    __table_args__ = (
        Index("ix_trust_factor_aggs_tenant_website_bucket", "tenant_id", "website_id", "bucket_start"),
        Index(
            "ix_trust_factor_aggs_tenant_website_path_bucket",
            "tenant_id",
            "website_id",
            "path",
            "bucket_start",
        ),
        Index("ix_trust_factor_aggs_tenant_factor", "tenant_id", "factor_type"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
    website_id = Column(Integer, ForeignKey("websites.id", ondelete="RESTRICT"), nullable=False, index=True)
    environment_id = Column(
        Integer,
        ForeignKey("website_environments.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    bucket_start = Column(DateTime, nullable=False, index=True)
    path = Column(String, nullable=True)
    factor_type = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    count = Column(Integer, nullable=False, default=0)
    evidence_json = Column(JSON_TYPE, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    is_demo = Column(Boolean, nullable=False, default=False)
