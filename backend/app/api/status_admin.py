from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies import require_platform_admin
from app.core.db import get_db
from app.core.platform import resolve_platform_audit_tenant_id
from app.crud.audit import create_audit_log
from app.crud.status_page import (
    add_incident_update,
    create_status_incident,
    ensure_status_components,
    list_admin_incidents,
    list_status_components,
    update_status_component,
    update_status_incident,
)
from app.schemas.status_page import (
    StatusComponentRead,
    StatusComponentUpdate,
    StatusIncidentCreate,
    StatusIncidentPatch,
    StatusIncidentRead,
    StatusIncidentUpdateCreate,
)


router = APIRouter(prefix="/admin/status", tags=["admin", "status"])


def _audit_platform_action(
    db: Session,
    *,
    username: str,
    event: str,
    request: Request | None = None,
) -> None:
    tenant_id = resolve_platform_audit_tenant_id(db)
    if tenant_id is None:
        return
    create_audit_log(db, tenant_id=tenant_id, username=username, event=event, request=request)


def _validate_components(db: Session, components: list[str]) -> list[str]:
    if not components:
        return []
    allowed = {row.key for row in ensure_status_components(db)}
    cleaned = [c.strip() for c in components if c and c.strip()]
    invalid = [c for c in cleaned if c not in allowed]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown components: {', '.join(invalid)}",
        )
    return cleaned


@router.get("/components", response_model=list[StatusComponentRead])
def admin_list_components(
    db: Session = Depends(get_db),
    current_user=Depends(require_platform_admin()),
):
    ensure_status_components(db)
    return list_status_components(db)


@router.patch("/components/{component_id}", response_model=StatusComponentRead)
def admin_update_component(
    component_id: int,
    payload: StatusComponentUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_platform_admin()),
):
    component = update_status_component(
        db,
        component_id,
        display_name=payload.display_name,
        current_status=payload.current_status,
    )
    if not component:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Component not found")
    _audit_platform_action(
        db,
        username=current_user.username,
        event=f"status.component.update:{component.key}",
        request=request,
    )
    return component


@router.get("/incidents", response_model=list[StatusIncidentRead])
def admin_list_incidents(
    db: Session = Depends(get_db),
    current_user=Depends(require_platform_admin()),
):
    return list_admin_incidents(db)


@router.post("/incidents", response_model=StatusIncidentRead, status_code=status.HTTP_201_CREATED)
def admin_create_incident(
    payload: StatusIncidentCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_platform_admin()),
):
    components = _validate_components(db, payload.components_affected)
    incident = create_status_incident(
        db,
        title=payload.title,
        status=payload.status,
        impact_level=payload.impact_level,
        components_affected=components,
        message=payload.message,
        is_published=payload.is_published,
    )
    _audit_platform_action(
        db,
        username=current_user.username,
        event="status.incident.create",
        request=request,
    )
    return incident


@router.patch("/incidents/{incident_id}", response_model=StatusIncidentRead)
def admin_update_incident(
    incident_id: int,
    payload: StatusIncidentPatch,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_platform_admin()),
):
    components = None
    if payload.components_affected is not None:
        components = _validate_components(db, payload.components_affected)
    incident = update_status_incident(
        db,
        incident_id,
        title=payload.title,
        status=payload.status,
        impact_level=payload.impact_level,
        components_affected=components,
        is_published=payload.is_published,
    )
    if not incident:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    _audit_platform_action(
        db,
        username=current_user.username,
        event="status.incident.update",
        request=request,
    )
    return incident


@router.post("/incidents/{incident_id}/updates", response_model=StatusIncidentRead)
def admin_add_incident_update(
    incident_id: int,
    payload: StatusIncidentUpdateCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_platform_admin()),
):
    incident = add_incident_update(
        db,
        incident_id,
        message=payload.message,
        status=payload.status,
    )
    if not incident:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    _audit_platform_action(
        db,
        username=current_user.username,
        event="status.incident.update_posted",
        request=request,
    )
    return incident


@router.post("/incidents/{incident_id}/publish", response_model=StatusIncidentRead)
def admin_publish_incident(
    incident_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_platform_admin()),
):
    incident = update_status_incident(db, incident_id, is_published=True)
    if not incident:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    _audit_platform_action(
        db,
        username=current_user.username,
        event="status.incident.publish",
        request=request,
    )
    return incident


@router.post("/incidents/{incident_id}/unpublish", response_model=StatusIncidentRead)
def admin_unpublish_incident(
    incident_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_platform_admin()),
):
    incident = update_status_incident(db, incident_id, is_published=False)
    if not incident:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    _audit_platform_action(
        db,
        username=current_user.username,
        event="status.incident.unpublish",
        request=request,
    )
    return incident
