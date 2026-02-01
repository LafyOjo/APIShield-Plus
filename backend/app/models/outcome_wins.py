from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint

from app.core.db import Base
from app.models.mixins import TimestampMixin


class OutcomeWin(TimestampMixin, Base):
    __tablename__ = "outcome_wins"
    __table_args__ = (
        UniqueConstraint("tenant_id", "incident_id", "metric_type", name="uq_outcome_wins_tenant_incident_metric"),
        Index("ix_outcome_wins_tenant_created", "tenant_id", "created_at"),
        Index("ix_outcome_wins_published", "is_published"),
        Index("ix_outcome_wins_slug", "share_slug"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
    incident_id = Column(Integer, ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True, index=True)
    metric_type = Column(String, nullable=False)
    metric_value = Column(Float, nullable=False)
    timeframe_start = Column(DateTime, nullable=False)
    timeframe_end = Column(DateTime, nullable=False)
    is_anonymized = Column(Boolean, nullable=False, default=True)
    is_published = Column(Boolean, nullable=False, default=False)
    share_slug = Column(String, nullable=True, unique=True, index=True)
    public_copy_text = Column(Text, nullable=True)
