from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.core.time import utcnow
from app.models.mixins import TimestampMixin


class TenantRetentionPolicy(TimestampMixin, Base):
    __tablename__ = "tenant_retention_policies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "dataset_key", name="uq_tenant_retention_dataset"),
        Index("ix_tenant_retention_tenant_dataset", "tenant_id", "dataset_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    dataset_key = Column(String, nullable=False)
    retention_days = Column(Integer, nullable=False)
    is_legal_hold_enabled = Column(Boolean, nullable=False, default=False)
    legal_hold_reason = Column(Text, nullable=True)
    legal_hold_enabled_at = Column(DateTime, nullable=True)
    updated_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    tenant = relationship("Tenant", back_populates="dataset_retention_policies", lazy="selectin")
    updated_by = relationship("User", foreign_keys=[updated_by_user_id], lazy="selectin")

    def enable_legal_hold(self, reason: str) -> None:
        self.is_legal_hold_enabled = True
        self.legal_hold_reason = reason
        self.legal_hold_enabled_at = utcnow()

    def disable_legal_hold(self) -> None:
        self.is_legal_hold_enabled = False
        self.legal_hold_reason = None
        self.legal_hold_enabled_at = None
