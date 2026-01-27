from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    JSON,
    Boolean,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.core.db import Base


JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class BehaviourEvent(Base):
    __tablename__ = "behaviour_events"
    __table_args__ = (
        Index("ix_behaviour_events_tenant_ingested_at", "tenant_id", "ingested_at"),
        Index(
            "ix_behaviour_events_tenant_website_ingested_at",
            "tenant_id",
            "website_id",
            "ingested_at",
        ),
        Index(
            "ix_behaviour_events_tenant_session_ingested_at",
            "tenant_id",
            "session_id",
            "ingested_at",
        ),
        Index(
            "ix_behaviour_events_tenant_session_event_ts",
            "tenant_id",
            "session_id",
            "event_ts",
        ),
        Index(
            "ix_behaviour_events_tenant_path_ingested_at",
            "tenant_id",
            "path",
            "ingested_at",
        ),
        Index(
            "ix_behaviour_events_tenant_ip_hash_ingested_at",
            "tenant_id",
            "ip_hash",
            "ingested_at",
        ),
        UniqueConstraint(
            "tenant_id",
            "environment_id",
            "event_id",
            name="uq_behaviour_events_tenant_env_event_id",
        ),
    )

    id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        index=True,
        autoincrement=True,
    )
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
    website_id = Column(Integer, ForeignKey("websites.id", ondelete="RESTRICT"), nullable=False, index=True)
    environment_id = Column(
        Integer,
        ForeignKey("website_environments.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    ingested_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    event_ts = Column(DateTime, nullable=False)
    event_id = Column(String, nullable=False)
    event_type = Column(String, nullable=False)
    url = Column(Text, nullable=False)
    path = Column(String, nullable=True)
    referrer = Column(Text, nullable=True)
    session_id = Column(String, nullable=True)
    visitor_id = Column(String, nullable=True)
    ip_hash = Column(String, nullable=True)
    user_agent = Column(Text, nullable=True)
    meta = Column(JSON_TYPE, nullable=True)
    is_demo = Column(Boolean, nullable=False, default=False)

    tenant = relationship("Tenant", back_populates="behaviour_events", lazy="noload")
    website = relationship("Website", back_populates="behaviour_events", lazy="noload")
    environment = relationship("WebsiteEnvironment", back_populates="behaviour_events", lazy="noload")
