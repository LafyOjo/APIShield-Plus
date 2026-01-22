from sqlalchemy import (
    BigInteger,
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


JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        Index(
            "ix_notification_deliveries_tenant_status_created",
            "tenant_id",
            "status",
            "created_at",
        ),
        UniqueConstraint(
            "tenant_id",
            "dedupe_key",
            name="uq_notification_deliveries_tenant_dedupe",
        ),
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
    rule_id = Column(
        Integer,
        ForeignKey("notification_rules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel_id = Column(
        Integer,
        ForeignKey("notification_channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status = Column(String, nullable=False, default="queued")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    sent_at = Column(DateTime, nullable=True)
    dedupe_key = Column(String, nullable=False)
    payload_json = Column(JSON_TYPE, nullable=False)
    error_message = Column(Text, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
