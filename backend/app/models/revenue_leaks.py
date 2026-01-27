from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    Boolean,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.core.db import Base


JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class RevenueLeakEstimate(Base):
    __tablename__ = "revenue_leak_estimates"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "website_id",
            "environment_id",
            "path",
            "bucket_start",
            name="uq_revenue_leak_tenant_path_bucket",
        ),
        Index(
            "ix_revenue_leak_tenant_site_bucket",
            "tenant_id",
            "website_id",
            "bucket_start",
        ),
        Index(
            "ix_revenue_leak_tenant_site_path_bucket",
            "tenant_id",
            "website_id",
            "path",
            "bucket_start",
        ),
    )

    id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        index=True,
        autoincrement=True,
    )
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

    baseline_conversion_rate = Column(Float, nullable=True)
    observed_conversion_rate = Column(Float, nullable=False)
    sessions_in_bucket = Column(Integer, nullable=False)
    expected_conversions = Column(Float, nullable=False)
    observed_conversions = Column(Integer, nullable=False)
    lost_conversions = Column(Float, nullable=False)
    revenue_per_conversion = Column(Float, nullable=True)
    estimated_lost_revenue = Column(Float, nullable=True)

    linked_trust_score = Column(Integer, nullable=True)
    confidence = Column(Float, nullable=False, default=0.5)
    explanation_json = Column(JSON_TYPE, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    is_demo = Column(Boolean, nullable=False, default=False)
