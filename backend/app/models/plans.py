from sqlalchemy import Boolean, Column, Integer, Numeric, String, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.models.mixins import TimestampMixin


JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class Plan(TimestampMixin, Base):
    __tablename__ = "plans"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True, index=True)
    price_monthly = Column(Numeric(10, 2), nullable=True)
    limits_json = Column(JSON_TYPE, nullable=False, default=dict)
    features_json = Column(JSON_TYPE, nullable=False, default=dict)
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    subscriptions = relationship("Subscription", back_populates="plan", lazy="selectin")
    feature_entitlements = relationship("FeatureEntitlement", back_populates="source_plan", lazy="selectin")
