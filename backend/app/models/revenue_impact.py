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
)
from sqlalchemy.dialects.postgresql import JSONB

from app.core.db import Base


JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class ConversionMetric(Base):
    __tablename__ = "conversion_metrics"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "website_id",
            "environment_id",
            "metric_key",
            "window_start",
            "window_end",
            name="uq_conversion_metrics_tenant_metric_window",
        ),
        Index(
            "ix_conversion_metrics_tenant_metric_window",
            "tenant_id",
            "metric_key",
            "window_start",
        ),
        Index(
            "ix_conversion_metrics_tenant_site_window",
            "tenant_id",
            "website_id",
            "environment_id",
            "window_start",
        ),
    )

    id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        index=True,
        autoincrement=True,
    )
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
    website_id = Column(Integer, ForeignKey("websites.id", ondelete="RESTRICT"), nullable=True, index=True)
    environment_id = Column(
        Integer,
        ForeignKey("website_environments.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    metric_key = Column(String, nullable=False)
    window_start = Column(DateTime, nullable=False)
    window_end = Column(DateTime, nullable=False)
    sessions = Column(Integer, nullable=False, default=0)
    conversions = Column(Integer, nullable=False, default=0)
    conversion_rate = Column(Float, nullable=False, default=0.0)
    revenue_per_conversion = Column(Float, nullable=True)
    captured_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class BaselineModel(Base):
    __tablename__ = "baseline_models"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "website_id",
            "environment_id",
            "metric_key",
            "method",
            name="uq_baseline_models_tenant_metric_method",
        ),
        Index(
            "ix_baseline_models_tenant_metric",
            "tenant_id",
            "metric_key",
        ),
        Index(
            "ix_baseline_models_tenant_site_metric",
            "tenant_id",
            "website_id",
            "environment_id",
            "metric_key",
        ),
    )

    id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        index=True,
        autoincrement=True,
    )
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
    website_id = Column(Integer, ForeignKey("websites.id", ondelete="RESTRICT"), nullable=True, index=True)
    environment_id = Column(
        Integer,
        ForeignKey("website_environments.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    metric_key = Column(String, nullable=False)
    baseline_rate = Column(Float, nullable=False)
    baseline_window_days = Column(Integer, nullable=False)
    baseline_updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    method = Column(String, nullable=False, default="rolling_avg")


class ImpactEstimate(Base):
    __tablename__ = "impact_estimates"
    __table_args__ = (
        Index(
            "ix_impact_estimates_tenant_metric_window",
            "tenant_id",
            "metric_key",
            "window_start",
        ),
        Index(
            "ix_impact_estimates_tenant_incident",
            "tenant_id",
            "incident_id",
        ),
        Index(
            "ix_impact_estimates_tenant_site_window",
            "tenant_id",
            "website_id",
            "environment_id",
            "window_start",
        ),
    )

    id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        index=True,
        autoincrement=True,
    )
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
    website_id = Column(Integer, ForeignKey("websites.id", ondelete="RESTRICT"), nullable=True, index=True)
    environment_id = Column(
        Integer,
        ForeignKey("website_environments.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    metric_key = Column(String, nullable=False)
    incident_id = Column(String, nullable=True)
    window_start = Column(DateTime, nullable=False)
    window_end = Column(DateTime, nullable=False)
    observed_rate = Column(Float, nullable=False)
    baseline_rate = Column(Float, nullable=False)
    delta_rate = Column(Float, nullable=False)
    estimated_lost_conversions = Column(Float, nullable=False)
    estimated_lost_revenue = Column(Float, nullable=True)
    confidence = Column(Float, nullable=False, default=0.5)
    explanation_json = Column(JSON_TYPE, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
