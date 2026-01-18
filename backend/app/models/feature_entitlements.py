from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.models.mixins import TimestampMixin


class FeatureEntitlement(TimestampMixin, Base):
    __tablename__ = "feature_entitlements"
    __table_args__ = (
        UniqueConstraint("tenant_id", "feature", name="uq_feature_entitlement"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    feature = Column(String, nullable=False)
    enabled = Column(Boolean, nullable=False, default=False)
    source = Column(String, nullable=False)
    source_plan_id = Column(
        Integer,
        ForeignKey("plans.id", ondelete="RESTRICT"),
        nullable=True,
    )
    updated_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    tenant = relationship("Tenant", back_populates="feature_entitlements", lazy="selectin")
    source_plan = relationship("Plan", back_populates="feature_entitlements", lazy="selectin")
    updated_by = relationship(
        "User",
        back_populates="updated_feature_entitlements",
        foreign_keys=[updated_by_user_id],
        lazy="selectin",
    )
