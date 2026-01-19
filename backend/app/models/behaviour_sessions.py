from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.db import Base


class BehaviourSession(Base):
    __tablename__ = "behaviour_sessions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "environment_id",
            "session_id",
            name="uq_behaviour_sessions_tenant_env_session_id",
        ),
        Index(
            "ix_behaviour_sessions_tenant_website_started_at",
            "tenant_id",
            "website_id",
            "started_at",
        ),
        Index(
            "ix_behaviour_sessions_tenant_session_id",
            "tenant_id",
            "session_id",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
    website_id = Column(Integer, ForeignKey("websites.id", ondelete="RESTRICT"), nullable=False, index=True)
    environment_id = Column(
        Integer,
        ForeignKey("website_environments.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    session_id = Column(String, nullable=False)
    started_at = Column(DateTime, nullable=False)
    last_seen_at = Column(DateTime, nullable=False)
    page_views = Column(Integer, nullable=False, default=0)
    event_count = Column(Integer, nullable=False, default=0)
    ip_hash = Column(String, nullable=True)
    entry_path = Column(String, nullable=True)
    exit_path = Column(String, nullable=True)
    country_code = Column(String, nullable=True)
    region = Column(String, nullable=True)
    city = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    asn = Column(String, nullable=True)
    is_datacenter = Column(Boolean, nullable=True)

    tenant = relationship("Tenant", back_populates="behaviour_sessions", lazy="noload")
    website = relationship("Website", back_populates="behaviour_sessions", lazy="noload")
    environment = relationship("WebsiteEnvironment", back_populates="behaviour_sessions", lazy="noload")
