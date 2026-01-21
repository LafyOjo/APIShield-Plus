from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.db import get_db
from app.crud.audit import create_audit_log
from app.crud.prescriptions import update_prescription_item_status
from app.crud.tenants import get_tenant_by_id, get_tenant_by_slug
from app.models.enums import RoleEnum
from app.models.prescriptions import PrescriptionItem
from app.schemas.prescriptions import PrescriptionItemRead, PrescriptionItemUpdate
from app.tenancy.dependencies import require_role_in_tenant


router = APIRouter(prefix="/prescriptions", tags=["prescriptions"])

def _resolve_tenant_id(db: Session, tenant_hint: str) -> int:
    if not tenant_hint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    tenant_value = tenant_hint.strip()
    tenant = (
        get_tenant_by_id(db, int(tenant_value))
        if tenant_value.isdigit()
        else get_tenant_by_slug(db, tenant_value)
    )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant.id


def _normalize_ts(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


@router.patch("/items/{item_id}", response_model=PrescriptionItemRead)
def update_prescription_item(
    item_id: int,
    payload: PrescriptionItemUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    ctx=Depends(require_role_in_tenant([RoleEnum.ANALYST, RoleEnum.ADMIN, RoleEnum.OWNER], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    item = (
        db.query(PrescriptionItem)
        .filter(PrescriptionItem.id == item_id, PrescriptionItem.tenant_id == tenant_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prescription item not found")

    changes = payload.dict(exclude_unset=True)
    next_status = changes.get("status")
    snoozed_until = _normalize_ts(changes.get("snoozed_until"))
    try:
        update_prescription_item_status(
            db,
            item=item,
            status=next_status,
            notes=changes.get("notes"),
            snoozed_until=snoozed_until,
            applied_by_user_id=ctx.user_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    status_event = None
    if next_status:
        if item.status == "applied":
            status_event = "prescription_applied"
        elif item.status == "dismissed":
            status_event = "prescription_dismissed"
        elif item.status == "snoozed":
            status_event = "prescription_snoozed"
    if status_event:
        event_label = f"{status_event}:{item.id}"
        create_audit_log(
            db,
            tenant_id=tenant_id,
            username=ctx.username or getattr(current_user, "username", None),
            event=event_label,
            request=request,
        )
    else:
        db.commit()

    db.refresh(item)
    return PrescriptionItemRead(
        id=item.id,
        bundle_id=item.bundle_id,
        incident_id=item.incident_id,
        key=item.key,
        title=item.title,
        priority=item.priority,
        effort=item.effort,
        expected_effect=item.expected_effect,
        status=item.status,
        applied_at=item.applied_at,
        dismissed_at=item.dismissed_at,
        snoozed_until=item.snoozed_until,
        notes=item.notes,
        applied_by_user_id=item.applied_by_user_id,
        evidence_json=item.evidence_json,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )
