from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.core.db import Base


JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class JobQueue(Base):
    __tablename__ = "job_queue"
    __table_args__ = (
        Index("ix_job_queue_queue_status_run_at", "queue_name", "status", "run_at"),
        Index("ix_job_queue_queue_priority_created", "queue_name", "priority", "created_at"),
        Index("ix_job_queue_tenant_queue_status", "tenant_id", "queue_name", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    queue_name = Column(String, nullable=False, index=True)
    job_type = Column(String, nullable=False, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True, index=True)
    payload_json = Column(JSON_TYPE, nullable=True)
    priority = Column(Integer, nullable=False, default=100)
    status = Column(String, nullable=False, default="queued")
    run_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    locked_at = Column(DateTime, nullable=True)
    locked_by = Column(String, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=True)
    last_error = Column(Text, nullable=True)
    last_attempt_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    tenant = relationship("Tenant", back_populates="queued_jobs", lazy="noload")
