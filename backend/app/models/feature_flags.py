from sqlalchemy import Boolean, Column, DateTime, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from app.core.db import Base
from app.core.time import utcnow
from app.models.mixins import TimestampMixin


JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class FeatureFlag(TimestampMixin, Base):
    __tablename__ = "feature_flags"
    __table_args__ = (
        UniqueConstraint("key", name="uq_feature_flags_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, nullable=False)
    is_enabled_global = Column(Boolean, nullable=False, default=False)
    rules_json = Column(JSON_TYPE, nullable=False, default=dict)


class Experiment(TimestampMixin, Base):
    __tablename__ = "experiments"
    __table_args__ = (
        UniqueConstraint("key", name="uq_experiments_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, nullable=False)
    variants_json = Column(JSON_TYPE, nullable=False, default=list)
    targeting_rules_json = Column(JSON_TYPE, nullable=False, default=dict)
    is_enabled = Column(Boolean, nullable=False, default=False)


class ExperimentAssignment(Base):
    __tablename__ = "experiment_assignments"
    __table_args__ = (
        UniqueConstraint("experiment_key", "tenant_id", "user_id", name="uq_experiment_assignments"),
        Index("ix_experiment_assignments_experiment", "experiment_key"),
        Index("ix_experiment_assignments_tenant", "tenant_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    experiment_key = Column(String, nullable=False)
    tenant_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, nullable=True)
    variant = Column(String, nullable=False)
    assigned_at = Column(DateTime, nullable=False, default=utcnow)
