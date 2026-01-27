from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.core.time import utcnow
from app.models.mixins import TimestampMixin


JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class OnboardingState(TimestampMixin, Base):
    __tablename__ = "onboarding_states"

    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    current_step = Column(String, nullable=False, default="create_website")
    completed_steps_json = Column(JSON_TYPE, nullable=False, default=list)
    last_updated_at = Column(DateTime, nullable=True, default=utcnow, onupdate=utcnow)
    verified_event_received_at = Column(DateTime, nullable=True)
    first_website_id = Column(
        Integer,
        ForeignKey("websites.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    tenant = relationship("Tenant", back_populates="onboarding_state", lazy="selectin")
    first_website = relationship("Website", lazy="selectin", foreign_keys=[first_website_id])
    created_by = relationship("User", lazy="selectin", foreign_keys=[created_by_user_id])
