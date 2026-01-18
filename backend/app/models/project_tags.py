from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.db import Base


class ProjectTag(Base):
    __tablename__ = "project_tags"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_project_tags_tenant_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name = Column(String, nullable=False)
    color = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    tenant = relationship("Tenant", back_populates="project_tags", lazy="selectin")
    websites = relationship(
        "Website",
        secondary="website_tags",
        back_populates="tags",
        lazy="selectin",
        passive_deletes=True,
    )


class WebsiteTag(Base):
    __tablename__ = "website_tags"

    website_id = Column(
        Integer,
        ForeignKey("websites.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    tag_id = Column(
        Integer,
        ForeignKey("project_tags.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )

    website = relationship("Website", lazy="selectin")
    tag = relationship("ProjectTag", lazy="selectin")
