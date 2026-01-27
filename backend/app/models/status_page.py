from sqlalchemy import Boolean, Column, DateTime, Enum, Index, Integer, String, JSON
from sqlalchemy.dialects.postgresql import JSONB

from app.core.db import Base
from app.core.time import utcnow
from app.models.enums import (
    StatusComponentStatusEnum,
    StatusImpactEnum,
    StatusIncidentStatusEnum,
)
from app.models.mixins import TimestampMixin


JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class StatusComponent(TimestampMixin, Base):
    __tablename__ = "status_components"
    __table_args__ = (
        Index("ix_status_components_key", "key", unique=True),
    )

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, nullable=False, unique=True)
    display_name = Column(String, nullable=False)
    current_status = Column(
        Enum(
            StatusComponentStatusEnum,
            name="status_component_status_enum",
            native_enum=False,
            validate_strings=True,
        ),
        nullable=False,
        default=StatusComponentStatusEnum.OPERATIONAL,
    )
    last_updated_at = Column(DateTime, nullable=True, default=utcnow)


class StatusIncident(TimestampMixin, Base):
    __tablename__ = "status_incidents"
    __table_args__ = (
        Index("ix_status_incidents_status", "status"),
        Index("ix_status_incidents_published", "is_published"),
    )

    id = Column(Integer, primary_key=True, index=True)
    status = Column(
        Enum(
            StatusIncidentStatusEnum,
            name="status_incident_status_enum",
            native_enum=False,
            validate_strings=True,
        ),
        nullable=False,
        default=StatusIncidentStatusEnum.INVESTIGATING,
    )
    impact_level = Column(
        Enum(
            StatusImpactEnum,
            name="status_incident_impact_enum",
            native_enum=False,
            validate_strings=True,
        ),
        nullable=False,
        default=StatusImpactEnum.MINOR,
    )
    title = Column(String, nullable=False)
    components_affected = Column(JSON_TYPE, nullable=False, default=list)
    updates = Column(JSON_TYPE, nullable=False, default=list)
    is_published = Column(Boolean, nullable=False, default=False)
    resolved_at = Column(DateTime, nullable=True)
