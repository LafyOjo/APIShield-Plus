from sqlalchemy import Column, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.models.mixins import TimestampMixin


class DataRetentionPolicy(TimestampMixin, Base):
    __tablename__ = "data_retention_policies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "event_type", name="uq_retention_tenant_event"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    event_type = Column(String, nullable=False)
    days = Column(Integer, nullable=False)

    tenant = relationship("Tenant", back_populates="retention_policies", lazy="selectin")
