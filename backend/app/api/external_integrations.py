from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_current_user
from app.core.db import get_db
from app.core.integrations import validate_integration_type
from app.crud.external_integrations import (
    create_integration,
    list_integrations,
    update_integration,
)
from app.crud.tenants import get_tenant_by_id, get_tenant_by_slug
from app.models.enums import RoleEnum
from app.schemas.external_integrations import (
    ExternalIntegrationCreate,
    ExternalIntegrationRead,
    ExternalIntegrationUpdate,
)
from app.tenancy.dependencies import require_roles


router = APIRouter(tags=["integrations"])


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


@router.get("/integrations", response_model=list[ExternalIntegrationRead])
def list_integrations_endpoint(
    db=Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    return list_integrations(db, tenant_id)


@router.post("/integrations", response_model=ExternalIntegrationRead)
def create_integration_endpoint(
    payload: ExternalIntegrationCreate,
    db=Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    try:
        validate_integration_type(payload.type)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    status_value = payload.status or "active"
    try:
        return create_integration(db, tenant_id, payload.type, payload.config, status=status_value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.patch("/integrations/{integration_id}", response_model=ExternalIntegrationRead)
def update_integration_endpoint(
    integration_id: int,
    payload: ExternalIntegrationUpdate,
    db=Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    try:
        integration = update_integration(
            db,
            tenant_id,
            integration_id,
            config=payload.config,
            status=payload.status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not integration:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")
    return integration
