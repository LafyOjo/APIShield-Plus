from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.enums import StatusComponentStatusEnum, StatusImpactEnum, StatusIncidentStatusEnum
from app.models.status_page import StatusComponent, StatusIncident

DEFAULT_STATUS_COMPONENTS = [
    {"key": "api", "display_name": "API"},
    {"key": "ingest", "display_name": "Ingest"},
    {"key": "geo", "display_name": "Geo"},
    {"key": "notifications", "display_name": "Notifications"},
    {"key": "dashboard", "display_name": "Dashboard"},
]


def ensure_status_components(db: Session) -> list[StatusComponent]:
    existing = {
        row.key: row
        for row in db.query(StatusComponent).order_by(StatusComponent.id.asc()).all()
    }
    missing = []
    for component in DEFAULT_STATUS_COMPONENTS:
        if component["key"] in existing:
            continue
        row = StatusComponent(
            key=component["key"],
            display_name=component["display_name"],
            current_status=StatusComponentStatusEnum.OPERATIONAL,
            last_updated_at=utcnow(),
        )
        db.add(row)
        missing.append(row)
    if missing:
        db.commit()
    return db.query(StatusComponent).order_by(StatusComponent.id.asc()).all()


def list_status_components(db: Session) -> list[StatusComponent]:
    return db.query(StatusComponent).order_by(StatusComponent.id.asc()).all()


def update_status_component(
    db: Session,
    component_id: int,
    *,
    display_name: str | None = None,
    current_status: StatusComponentStatusEnum | None = None,
) -> StatusComponent | None:
    component = db.query(StatusComponent).filter(StatusComponent.id == component_id).first()
    if not component:
        return None
    if display_name is not None:
        component.display_name = display_name.strip()
    if current_status is not None:
        component.current_status = current_status
        component.last_updated_at = utcnow()
    db.commit()
    db.refresh(component)
    return component


def list_public_incidents(db: Session) -> list[StatusIncident]:
    return (
        db.query(StatusIncident)
        .filter(StatusIncident.is_published.is_(True))
        .order_by(StatusIncident.created_at.desc())
        .all()
    )


def list_admin_incidents(db: Session) -> list[StatusIncident]:
    return db.query(StatusIncident).order_by(StatusIncident.created_at.desc()).all()


def create_status_incident(
    db: Session,
    *,
    title: str,
    status: StatusIncidentStatusEnum = StatusIncidentStatusEnum.INVESTIGATING,
    impact_level: StatusImpactEnum = StatusImpactEnum.MINOR,
    components_affected: list[str] | None = None,
    message: str | None = None,
    is_published: bool = False,
) -> StatusIncident:
    updates: list[dict] = []
    if message:
        updates.append(
            {
                "timestamp": utcnow().isoformat(),
                "message": message.strip(),
                "status": status.value,
            }
        )
    incident = StatusIncident(
        title=title.strip(),
        status=status,
        impact_level=impact_level,
        components_affected=components_affected or [],
        updates=updates,
        is_published=is_published,
        resolved_at=utcnow() if status == StatusIncidentStatusEnum.RESOLVED else None,
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident


def update_status_incident(
    db: Session,
    incident_id: int,
    *,
    title: str | None = None,
    status: StatusIncidentStatusEnum | None = None,
    impact_level: StatusImpactEnum | None = None,
    components_affected: list[str] | None = None,
    is_published: bool | None = None,
) -> StatusIncident | None:
    incident = db.query(StatusIncident).filter(StatusIncident.id == incident_id).first()
    if not incident:
        return None
    if title is not None:
        incident.title = title.strip()
    if status is not None:
        incident.status = status
        if status == StatusIncidentStatusEnum.RESOLVED:
            incident.resolved_at = utcnow()
    if impact_level is not None:
        incident.impact_level = impact_level
    if components_affected is not None:
        incident.components_affected = components_affected
    if is_published is not None:
        incident.is_published = is_published
    db.commit()
    db.refresh(incident)
    return incident


def add_incident_update(
    db: Session,
    incident_id: int,
    *,
    message: str,
    status: StatusIncidentStatusEnum | None = None,
) -> StatusIncident | None:
    incident = db.query(StatusIncident).filter(StatusIncident.id == incident_id).first()
    if not incident:
        return None
    updates = list(incident.updates or [])
    updates.append(
        {
            "timestamp": utcnow().isoformat(),
            "message": message.strip(),
            "status": status.value if status else incident.status.value,
        }
    )
    incident.updates = updates
    if status is not None:
        incident.status = status
        if status == StatusIncidentStatusEnum.RESOLVED:
            incident.resolved_at = utcnow()
    db.commit()
    db.refresh(incident)
    return incident
