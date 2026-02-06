from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.core.db import Base


JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class JobDeadLetter(Base):
    __tablename__ = "job_dead_letters"
    __table_args__ = (
        Index("ix_job_dead_letters_queue_failed_at", "queue_name", "failed_at"),
        Index("ix_job_dead_letters_tenant", "tenant_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    original_job_id = Column(Integer, nullable=True)
    queue_name = Column(String, nullable=False, index=True)
    job_type = Column(String, nullable=False, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True, index=True)
    payload_json = Column(JSON_TYPE, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    last_attempt_at = Column(DateTime, nullable=True)
    failed_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    tenant = relationship("Tenant", back_populates="dead_letter_jobs", lazy="noload")
