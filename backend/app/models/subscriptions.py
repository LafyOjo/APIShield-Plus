from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.models.mixins import TimestampMixin


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    plan_id = Column(
        Integer,
        ForeignKey("plans.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    provider = Column(String, nullable=False, default="manual")
    provider_subscription_id = Column(String, nullable=True)
    status = Column(String, nullable=False, default="active", index=True)
    current_period_start = Column(DateTime, nullable=True)
    current_period_end = Column(DateTime, nullable=True, index=True)
    cancel_at_period_end = Column(Boolean, default=False, nullable=False)

    tenant = relationship("Tenant", back_populates="subscriptions", lazy="selectin")
    plan = relationship("Plan", back_populates="subscriptions", lazy="selectin")
