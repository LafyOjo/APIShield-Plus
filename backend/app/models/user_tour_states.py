from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.core.time import utcnow
from app.models.mixins import TimestampMixin


JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class UserTourState(TimestampMixin, Base):
    __tablename__ = "user_tour_states"

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    tours_completed_json = Column(JSON_TYPE, nullable=False, default=list)
    tours_dismissed_json = Column(JSON_TYPE, nullable=False, default=list)
    last_updated_at = Column(DateTime, nullable=True, default=utcnow, onupdate=utcnow)

    user = relationship("User", lazy="selectin")
    tenant = relationship("Tenant", lazy="selectin")
