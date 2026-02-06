from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_current_user
from app.core.branding import (
    apply_branding_policy_to_payload,
    build_domain_verification_record,
)
from app.core.config import settings
from app.core.db import get_db
from app.crud.tenant_branding import get_or_create_branding, mark_domain_verified, update_branding
from app.crud.tenants import get_tenant_by_id, get_tenant_by_slug
from app.entitlements.resolver import resolve_entitlements_for_tenant
from app.models.enums import RoleEnum
from app.schemas.tenant_branding import TenantBrandingRead, TenantBrandingUpdate
from app.tenancy.dependencies import require_roles


router = APIRouter(tags=["branding"])


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


def _serialize_branding(branding, plan_key: str | None) -> TenantBrandingRead:
    payload = {
        "tenant_id": branding.tenant_id,
        "is_enabled": branding.is_enabled,
        "brand_name": branding.brand_name,
        "logo_url": branding.logo_url,
        "primary_color": branding.primary_color,
        "accent_color": branding.accent_color,
        "custom_domain": branding.custom_domain,
        "domain_verified_at": branding.domain_verified_at,
        "badge_branding_mode": branding.badge_branding_mode,
        "updated_at": branding.updated_at,
    }
    payload = apply_branding_policy_to_payload(payload, plan_key)
    txt_name, txt_value = build_domain_verification_record(
        payload.get("custom_domain"),
        branding.domain_verification_token,
    )
    payload["verification_txt_name"] = txt_name
    payload["verification_txt_value"] = txt_value
    return TenantBrandingRead(**payload)


@router.get("/branding", response_model=TenantBrandingRead)
def get_branding(
    db=Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    branding = get_or_create_branding(db, tenant_id)
    entitlements = resolve_entitlements_for_tenant(db, tenant_id)
    return _serialize_branding(branding, entitlements.get("plan_key"))


@router.patch("/branding", response_model=TenantBrandingRead)
def update_branding_endpoint(
    payload: TenantBrandingUpdate,
    db=Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    entitlements = resolve_entitlements_for_tenant(db, tenant_id)
    branding = update_branding(
        db,
        tenant_id,
        payload.dict(exclude_unset=True),
        plan_key=entitlements.get("plan_key"),
    )
    return _serialize_branding(branding, entitlements.get("plan_key"))


@router.post("/branding/verify", response_model=TenantBrandingRead)
def verify_branding_domain(
    db=Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    branding = get_or_create_branding(db, tenant_id)
    if not branding.custom_domain:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Custom domain not set")
    if settings.ENVIRONMENT == "production":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="DNS verification not enabled yet",
        )
    verified = mark_domain_verified(db, tenant_id)
    entitlements = resolve_entitlements_for_tenant(db, tenant_id)
    return _serialize_branding(verified, entitlements.get("plan_key"))
