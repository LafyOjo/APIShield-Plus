from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_current_user
from app.core.db import get_db
from app.crud.data_exports import get_export_config, update_export_config, upsert_export_config
from app.crud.tenants import get_tenant_by_id, get_tenant_by_slug
from app.entitlements.enforcement import require_feature
from app.entitlements.resolver import resolve_entitlements_for_tenant
from app.models.enums import RoleEnum
from app.schemas.data_exports import (
    DataExportConfigRead,
    DataExportConfigUpdate,
    DataExportConfigUpsert,
)
from app.tenancy.dependencies import require_roles


router = APIRouter(prefix="/exports", tags=["exports"])


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


@router.get("/config", response_model=DataExportConfigRead)
def read_export_config(
    db=Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    entitlements = resolve_entitlements_for_tenant(db, tenant_id)
    require_feature(entitlements, "data_exports", message="Data exports require a Business plan")
    config = get_export_config(db, tenant_id)
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export config not found")
    return config


@router.post("/config", response_model=DataExportConfigRead)
def upsert_export_config_endpoint(
    payload: DataExportConfigUpsert,
    db=Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    entitlements = resolve_entitlements_for_tenant(db, tenant_id)
    require_feature(entitlements, "data_exports", message="Data exports require a Business plan")
    try:
        return upsert_export_config(
            db,
            tenant_id,
            target_type=payload.target_type,
            target_config=payload.target_config,
            schedule=payload.schedule,
            datasets_enabled=payload.datasets_enabled,
            format_value=payload.format,
            is_enabled=payload.is_enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.patch("/config", response_model=DataExportConfigRead)
def update_export_config_endpoint(
    payload: DataExportConfigUpdate,
    db=Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    entitlements = resolve_entitlements_for_tenant(db, tenant_id)
    require_feature(entitlements, "data_exports", message="Data exports require a Business plan")
    try:
        config = update_export_config(
            db,
            tenant_id,
            target_type=payload.target_type,
            target_config=payload.target_config,
            schedule=payload.schedule,
            datasets_enabled=payload.datasets_enabled,
            format_value=payload.format,
            is_enabled=payload.is_enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export config not found")
    return config
