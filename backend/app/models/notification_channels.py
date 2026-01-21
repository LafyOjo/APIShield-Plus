from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.models.mixins import TimestampMixin


JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class NotificationChannel(TimestampMixin, Base):
    __tablename__ = "notification_channels"
    __table_args__ = (
        Index(
            "ix_notification_channels_tenant_type_enabled",
            "tenant_id",
            "type",
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
    type = Column(String, nullable=False)
    name = Column(String, nullable=False)
    is_enabled = Column(Boolean, nullable=False, default=True)
    created_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    config_public_json = Column(JSON_TYPE, nullable=True)
    config_secret_enc = Column(Text, nullable=True)
    categories_allowed = Column(JSON_TYPE, nullable=True)
    last_tested_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)

    tenant = relationship("Tenant", back_populates="notification_channels", lazy="selectin")

    @property
    def is_configured(self) -> bool:
        return bool(self.config_secret_enc)
