from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.models.mixins import TimestampMixin


class ExternalIntegration(TimestampMixin, Base):
    __tablename__ = "external_integrations"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    type = Column(String, nullable=False)
    config_encrypted = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="active")
    last_error = Column(Text, nullable=True)

    tenant = relationship("Tenant", back_populates="external_integrations", lazy="selectin")
