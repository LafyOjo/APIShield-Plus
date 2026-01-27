from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import get_current_user
from app.core.db import get_db
from app.crud.audit import create_audit_log
from app.crud.scim import get_scim_config, rotate_scim_token, upsert_scim_config
from app.crud.tenants import get_tenant_by_id, get_tenant_by_slug
from app.entitlements.enforcement import require_feature
from app.entitlements.resolver import resolve_entitlements_for_tenant
from app.models.enums import RoleEnum
from app.schemas.scim import SCIMTokenRotateResponse, TenantSCIMConfigRead, TenantSCIMConfigUpsert
from app.tenancy.dependencies import require_roles


router = APIRouter(prefix="/scim", tags=["scim-config"])


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


@router.get("/config", response_model=TenantSCIMConfigRead)
def read_scim_config(
    db=Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    entitlements = resolve_entitlements_for_tenant(db, tenant_id)
    require_feature(entitlements, "scim", message="SCIM requires an Enterprise plan")
    config = get_scim_config(db, tenant_id)
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SCIM config not found")
    return config


@router.post("/config", response_model=TenantSCIMConfigRead)
def upsert_scim_config_endpoint(
    payload: TenantSCIMConfigUpsert,
    request: Request,
    db=Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    entitlements = resolve_entitlements_for_tenant(db, tenant_id)
    require_feature(entitlements, "scim", message="SCIM requires an Enterprise plan")
    try:
        config = upsert_scim_config(
            db,
            tenant_id,
            is_enabled=payload.is_enabled,
            default_role=payload.default_role,
            group_role_mappings=payload.group_role_mappings_json,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    create_audit_log(
        db,
        tenant_id=tenant_id,
        username=ctx.username,
        event="scim_config_updated",
        request=request,
    )
    return config


@router.post("/token/rotate", response_model=SCIMTokenRotateResponse)
def rotate_scim_token_endpoint(
    request: Request,
    db=Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    entitlements = resolve_entitlements_for_tenant(db, tenant_id)
    require_feature(entitlements, "scim", message="SCIM requires an Enterprise plan")
    config, token = rotate_scim_token(db, tenant_id)
    create_audit_log(
        db,
        tenant_id=tenant_id,
        username=ctx.username,
        event="scim_token_rotated",
        request=request,
    )
    return SCIMTokenRotateResponse(
        scim_token=token,
        token_last_rotated_at=config.token_last_rotated_at,
    )
