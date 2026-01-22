from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, String

from app.core.db import Base
from app.core.time import utcnow
from app.models.mixins import TimestampMixin


class BackfillRun(TimestampMixin, Base):
    __tablename__ = "backfill_runs"
    __table_args__ = (Index("ix_backfill_runs_job_name", "job_name"),)

    id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        index=True,
        autoincrement=True,
    )
    job_name = Column(String, nullable=False, index=True)
    started_at = Column(DateTime, nullable=False, default=utcnow)
    finished_at = Column(DateTime, nullable=True)
    last_id_processed = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        nullable=True,
    )
