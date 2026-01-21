from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.core.db import Base
from app.core.time import utcnow
from app.models.mixins import TimestampMixin


JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class NotificationRule(TimestampMixin, Base):
    __tablename__ = "notification_rules"
    __table_args__ = (
        Index(
            "ix_notification_rules_tenant_trigger",
            "tenant_id",
            "trigger_type",
        ),
        Index(
            "ix_notification_rules_tenant_enabled",
            "tenant_id",
            "is_enabled",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name = Column(String, nullable=False)
    is_enabled = Column(Boolean, nullable=False, default=True)
    trigger_type = Column(String, nullable=False)
    filters_json = Column(JSON_TYPE, nullable=True)
    thresholds_json = Column(JSON_TYPE, nullable=True)
    quiet_hours_json = Column(JSON_TYPE, nullable=True)
    created_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


class NotificationRuleChannel(Base):
    __tablename__ = "notification_rule_channels"
    __table_args__ = (
        Index(
            "ix_notification_rule_channels_channel",
            "channel_id",
        ),
    )

    rule_id = Column(
        Integer,
        ForeignKey("notification_rules.id", ondelete="CASCADE"),
        primary_key=True,
    )
    channel_id = Column(
        Integer,
        ForeignKey("notification_channels.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at = Column(DateTime, nullable=False, default=utcnow)
