from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.core.db import Base
from app.models.mixins import TimestampMixin


JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class Incident(TimestampMixin, Base):
    __tablename__ = "incidents"
    __table_args__ = (
        Index(
            "ix_incidents_tenant_status_last_seen",
            "tenant_id",
            "status",
            "last_seen_at",
        ),
        Index(
            "ix_incidents_tenant_category_last_seen",
            "tenant_id",
            "category",
            "last_seen_at",
        ),
        Index(
            "ix_incidents_tenant_site_last_seen",
            "tenant_id",
            "website_id",
            "environment_id",
            "last_seen_at",
        ),
        Index(
            "ix_incidents_tenant_impact",
            "tenant_id",
            "impact_estimate_id",
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
    status = Column(String, nullable=False, default="open")
    status_manual = Column(Boolean, nullable=False, default=False)
    category = Column(String, nullable=False)
    title = Column(String, nullable=False)
    summary = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    severity = Column(String, nullable=False)
    first_seen_at = Column(DateTime, nullable=False)
    last_seen_at = Column(DateTime, nullable=False)
    primary_ip_hash = Column(String, nullable=True)
    primary_country_code = Column(String, nullable=True)
    evidence_json = Column(JSON_TYPE, nullable=True)
    impact_estimate_id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("impact_estimates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    prescription_bundle_id = Column(String, nullable=True)
    assigned_to_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


class IncidentSecurityEventLink(Base):
    __tablename__ = "incident_security_event_links"

    incident_id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    security_event_id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("security_events.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class IncidentAnomalySignalLink(Base):
    __tablename__ = "incident_anomaly_signal_links"

    incident_id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    anomaly_signal_id = Column(
        Integer,
        ForeignKey("anomaly_signal_events.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class IncidentRecovery(Base):
    __tablename__ = "incident_recoveries"
    __table_args__ = (
        Index(
            "ix_incident_recoveries_tenant_incident",
            "tenant_id",
            "incident_id",
        ),
        Index(
            "ix_incident_recoveries_tenant_measured_at",
            "tenant_id",
            "measured_at",
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
    incident_id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    measured_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    window_start = Column(DateTime, nullable=False)
    window_end = Column(DateTime, nullable=False)
    post_conversion_rate = Column(Float, nullable=False, default=0.0)
    change_in_errors = Column(Float, nullable=True)
    change_in_threats = Column(Float, nullable=True)
    recovery_ratio = Column(Float, nullable=False, default=0.0)
    confidence = Column(Float, nullable=False, default=0.5)
    evidence_json = Column(JSON_TYPE, nullable=True)
