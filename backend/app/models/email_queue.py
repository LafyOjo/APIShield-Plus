from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    JSON,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.models.mixins import TimestampMixin


JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class EmailQueue(TimestampMixin, Base):
    __tablename__ = "email_queue"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "user_id",
            "dedupe_key",
            name="uq_email_queue_dedupe",
        ),
        Index("ix_email_queue_tenant_status_created", "tenant_id", "status", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    to_email = Column(String, nullable=False)
    template_key = Column(String, nullable=False)
    dedupe_key = Column(String, nullable=False)
    trigger_event = Column(String, nullable=True)
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="queued")
    sent_at = Column(DateTime, nullable=True)
    metadata_json = Column(JSON_TYPE, nullable=True)

    tenant = relationship("Tenant", lazy="selectin")
    user = relationship("User", lazy="selectin")
