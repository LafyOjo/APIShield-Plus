from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.models.mixins import TimestampMixin


class TenantSSOConfig(TimestampMixin, Base):
    __tablename__ = "tenant_sso_configs"

    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    provider = Column(String, nullable=False, default="oidc")
    is_enabled = Column(Boolean, nullable=False, default=False)
    issuer_url = Column(String, nullable=True)
    client_id = Column(String, nullable=True)
    client_secret_enc = Column(Text, nullable=True)
    redirect_uri = Column(String, nullable=True)
    scopes = Column(String, nullable=True, default="openid email profile")
    idp_entity_id = Column(String, nullable=True)
    idp_sso_url = Column(String, nullable=True)
    idp_x509_cert = Column(Text, nullable=True)
    sp_entity_id = Column(String, nullable=True)
    sp_acs_url = Column(String, nullable=True)
    sp_x509_cert = Column(Text, nullable=True)
    allowed_email_domains = Column(JSON, nullable=True, default=list)
    sso_required = Column(Boolean, nullable=False, default=False)
    auto_provision = Column(Boolean, nullable=False, default=False)
    last_tested_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)

    tenant = relationship("Tenant", back_populates="sso_config", lazy="selectin")
