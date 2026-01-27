from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.core.time import utcnow
from app.models.mixins import TimestampMixin


class RetentionRun(TimestampMixin, Base):
    __tablename__ = "retention_runs"
    __table_args__ = (
        Index("ix_retention_runs_tenant_started_at", "tenant_id", "started_at"),
    )

    id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        index=True,
        autoincrement=True,
    )
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    started_at = Column(DateTime, nullable=False, default=utcnow)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String, nullable=False, default="running")
    event_retention_days = Column(Integer, nullable=False)
    raw_ip_retention_days = Column(Integer, nullable=False)
    behaviour_events_deleted = Column(Integer, nullable=False, default=0)
    security_events_deleted = Column(Integer, nullable=False, default=0)
    alerts_raw_ip_scrubbed = Column(Integer, nullable=False, default=0)
    events_raw_ip_scrubbed = Column(Integer, nullable=False, default=0)
    audit_logs_raw_ip_scrubbed = Column(Integer, nullable=False, default=0)
    security_events_raw_ip_scrubbed = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)

    tenant = relationship("Tenant", lazy="selectin")
