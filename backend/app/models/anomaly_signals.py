from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, JSON
from sqlalchemy.dialects.postgresql import JSONB

from app.core.db import Base


JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class AnomalySignalEvent(Base):
    __tablename__ = "anomaly_signal_events"
    __table_args__ = (
        Index("ix_anomaly_signals_tenant_created_at", "tenant_id", "created_at"),
        Index("ix_anomaly_signals_tenant_signal_type", "tenant_id", "signal_type"),
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
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    signal_type = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    session_id = Column(String, nullable=True)
    event_id = Column(String, nullable=True)
    summary = Column(JSON_TYPE, nullable=True)
