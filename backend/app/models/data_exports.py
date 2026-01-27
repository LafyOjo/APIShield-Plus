from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.core.db import Base
from app.core.time import utcnow
from app.models.mixins import TimestampMixin


JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class DataExportConfig(TimestampMixin, Base):
    __tablename__ = "data_export_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_data_export_configs_tenant"),
        Index("ix_data_export_configs_tenant_enabled", "tenant_id", "is_enabled"),
    )

    id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        index=True,
        autoincrement=True,
    )
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
    is_enabled = Column(Boolean, nullable=False, default=True)
    target_type = Column(String, nullable=False)
    target_secret_enc = Column(Text, nullable=True)
    schedule = Column(String, nullable=False, default="daily")
    datasets_enabled = Column(JSON_TYPE, nullable=False, default=list)
    format = Column(String, nullable=False, default="jsonl.gz")
    last_run_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)


class DataExportRun(Base):
    __tablename__ = "data_export_runs"
    __table_args__ = (
        Index("ix_data_export_runs_tenant_started_at", "tenant_id", "started_at"),
        Index("ix_data_export_runs_config_started_at", "config_id", "started_at"),
    )

    id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        index=True,
        autoincrement=True,
    )
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
    config_id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("data_export_configs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    started_at = Column(DateTime, nullable=False, default=utcnow)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String, nullable=False, default="running")
    files_written = Column(Integer, nullable=False, default=0)
    bytes_written = Column(BigInteger().with_variant(Integer, "sqlite"), nullable=False, default=0)
    error_message = Column(Text, nullable=True)
