from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.models.mixins import TimestampMixin


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        Index("ix_subscriptions_stripe_customer", "stripe_customer_id"),
        Index("ix_subscriptions_stripe_subscription", "stripe_subscription_id"),
        Index("ix_subscriptions_plan_key", "plan_key"),
    )

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
    plan_key = Column(String, nullable=True, index=True)
    provider = Column(String, nullable=False, default="manual")
    provider_subscription_id = Column(String, nullable=True)
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)
    seats = Column(Integer, nullable=True)
    status = Column(String, nullable=False, default="active", index=True)
    current_period_start = Column(DateTime, nullable=True)
    current_period_end = Column(DateTime, nullable=True, index=True)
    cancel_at_period_end = Column(Boolean, default=False, nullable=False)

    tenant = relationship("Tenant", back_populates="subscriptions", lazy="selectin")
    plan = relationship("Plan", back_populates="subscriptions", lazy="selectin")
