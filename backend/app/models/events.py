from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String
from app.core.db import Base


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_tenant_time", "tenant_id", "timestamp"),
        Index("ix_events_tenant_ip_hash_time", "tenant_id", "ip_hash", "timestamp"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    username = Column(String, nullable=True, index=True)
    action = Column(String, nullable=False)
    success = Column(Boolean, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    client_ip = Column(String, nullable=True)
    ip_hash = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    request_path = Column(String, nullable=True)
    referrer = Column(String, nullable=True)
    country_code = Column(String, nullable=True)
    region = Column(String, nullable=True)
    city = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    asn = Column(String, nullable=True)
    is_datacenter = Column(Boolean, nullable=True)
