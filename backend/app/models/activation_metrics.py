from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.models.mixins import TimestampMixin


JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class ActivationMetric(TimestampMixin, Base):
    __tablename__ = "activation_metrics"
    __table_args__ = (
        Index("ix_activation_metrics_score", "activation_score"),
    )

    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    time_to_first_event_seconds = Column(Integer, nullable=True)
    onboarding_completed_at = Column(DateTime, nullable=True)
    first_alert_created_at = Column(DateTime, nullable=True)
    first_incident_viewed_at = Column(DateTime, nullable=True)
    first_prescription_applied_at = Column(DateTime, nullable=True)
    activation_score = Column(Integer, nullable=False, default=0)
    notes_json = Column(JSON_TYPE, nullable=True)

    tenant = relationship("Tenant", back_populates="activation_metric", lazy="selectin")
