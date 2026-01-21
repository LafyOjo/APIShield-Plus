from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.core.db import Base
from app.models.mixins import TimestampMixin


JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class PrescriptionBundle(Base):
    __tablename__ = "prescription_bundles"
    __table_args__ = (
        Index(
            "ix_prescription_bundles_tenant_incident",
            "tenant_id",
            "incident_id",
        ),
        Index(
            "ix_prescription_bundles_tenant_created_at",
            "tenant_id",
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
    incident_id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    items_json = Column(JSON_TYPE, nullable=False, default=list)
    status = Column(String, nullable=False, default="suggested")
    notes = Column(String, nullable=True)


class PrescriptionItem(TimestampMixin, Base):
    __tablename__ = "prescription_items"
    __table_args__ = (
        Index(
            "ix_prescription_items_tenant_incident",
            "tenant_id",
            "incident_id",
        ),
        Index(
            "ix_prescription_items_tenant_status",
            "tenant_id",
            "status",
        ),
        Index(
            "ix_prescription_items_bundle",
            "bundle_id",
        ),
    )

    id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        index=True,
        autoincrement=True,
    )
    bundle_id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("prescription_bundles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
    website_id = Column(Integer, ForeignKey("websites.id", ondelete="RESTRICT"), nullable=True, index=True)
    environment_id = Column(
        Integer,
        ForeignKey("website_environments.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    incident_id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    priority = Column(String, nullable=False)
    effort = Column(String, nullable=False)
    expected_effect = Column(String, nullable=False)
    status = Column(String, nullable=False, default="suggested")
    applied_at = Column(DateTime, nullable=True)
    dismissed_at = Column(DateTime, nullable=True)
    snoozed_until = Column(DateTime, nullable=True)
    notes = Column(String, nullable=True)
    applied_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    evidence_json = Column(JSON_TYPE, nullable=True)
