from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_current_user
from app.core.db import get_db
from app.core.retention import validate_event_type
from app.crud.data_retention import get_policies, upsert_policy
from app.crud.tenants import get_tenant_by_id, get_tenant_by_slug
from app.models.enums import RoleEnum
from app.schemas.data_retention import DataRetentionRead, DataRetentionUpdate
from app.tenancy.dependencies import require_roles, require_tenant_context


router = APIRouter(tags=["data-retention"])


def _resolve_tenant_id(db, tenant_hint: str) -> int:
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


@router.get("/retention", response_model=list[DataRetentionRead])
def list_retention(
    db=Depends(get_db),
    ctx=Depends(require_tenant_context(user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    return get_policies(db, tenant_id)


@router.patch("/retention", response_model=DataRetentionRead)
def update_retention(
    payload: DataRetentionUpdate,
    db=Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    try:
        validate_event_type(payload.event_type)
        return upsert_policy(db, tenant_id, payload.event_type, payload.days)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
