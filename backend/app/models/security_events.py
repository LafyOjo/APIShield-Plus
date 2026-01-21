from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.core.db import Base


JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class SecurityEvent(Base):
    __tablename__ = "security_events"
    __table_args__ = (
        Index("ix_security_events_tenant_created_at", "tenant_id", "created_at"),
        Index(
            "ix_security_events_tenant_category_created_at",
            "tenant_id",
            "category",
            "created_at",
        ),
        Index(
            "ix_security_events_tenant_event_type_created_at",
            "tenant_id",
            "event_type",
            "created_at",
        ),
        Index(
            "ix_security_events_tenant_ip_hash_created_at",
            "tenant_id",
            "ip_hash",
            "created_at",
        ),
        Index(
            "ix_security_events_tenant_website_created_at",
            "tenant_id",
            "website_id",
            "created_at",
        ),
    )

    id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        index=True,
        autoincrement=True,
    )
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
    website_id = Column(Integer, ForeignKey("websites.id", ondelete="RESTRICT"), nullable=True, index=True)
    environment_id = Column(
        Integer,
        ForeignKey("website_environments.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    event_ts = Column(DateTime, nullable=True, default=datetime.utcnow)
    category = Column(String, nullable=False)
    event_type = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    source = Column(String, nullable=False)
    request_path = Column(String, nullable=True)
    method = Column(String, nullable=True)
    status_code = Column(Integer, nullable=True)
    user_identifier = Column(String, nullable=True)
    session_id = Column(String, nullable=True)
    client_ip = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    ip_hash = Column(String, nullable=True)
    country_code = Column(String, nullable=True)
    region = Column(String, nullable=True)
    city = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    asn_number = Column(Integer, nullable=True)
    asn_org = Column(String, nullable=True)
    is_datacenter = Column(Boolean, nullable=True)
    meta = Column(JSON_TYPE, nullable=True)
