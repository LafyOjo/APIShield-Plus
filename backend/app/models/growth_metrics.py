from datetime import date

from sqlalchemy import Column, Date, Float, Integer, JSON, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB

from app.core.db import Base
from app.models.mixins import TimestampMixin


JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class GrowthSnapshot(TimestampMixin, Base):
    __tablename__ = "growth_snapshots"
    __table_args__ = (
        UniqueConstraint("snapshot_date", name="uq_growth_snapshot_date"),
        Index("ix_growth_snapshot_date", "snapshot_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    snapshot_date = Column(Date, nullable=False, unique=True)
    signups = Column(Integer, nullable=False, default=0)
    activated = Column(Integer, nullable=False, default=0)
    onboarding_completed = Column(Integer, nullable=False, default=0)
    first_incident = Column(Integer, nullable=False, default=0)
    first_prescription = Column(Integer, nullable=False, default=0)
    upgraded = Column(Integer, nullable=False, default=0)
    churned = Column(Integer, nullable=False, default=0)
    avg_time_to_first_event_seconds = Column(Float, nullable=True)
    funnel_json = Column(JSON_TYPE, nullable=True)
    cohort_json = Column(JSON_TYPE, nullable=True)
    paywall_json = Column(JSON_TYPE, nullable=True)
