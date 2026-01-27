from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_current_user
from app.core.db import get_db
from app.core.retention import validate_dataset_key
from app.core.entitlements import invalidate_entitlement_cache
from app.crud.audit import create_audit_log
from app.crud.tenants import get_tenant_by_id, get_tenant_by_slug
from app.crud.tenant_retention_policies import get_policies, upsert_policy
from app.entitlements.enforcement import require_feature
from app.entitlements.resolver import resolve_entitlements_for_tenant
from app.models.enums import RoleEnum
from app.models.tenant_retention_policies import TenantRetentionPolicy
from app.schemas.tenant_retention import TenantRetentionPolicyRead, TenantRetentionPolicyUpdate
from app.tenancy.dependencies import require_roles, require_tenant_context


router = APIRouter(tags=["tenant-retention"])


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


@router.get("/retention/policies", response_model=list[TenantRetentionPolicyRead])
def list_retention_policies(
    db=Depends(get_db),
    ctx=Depends(require_tenant_context(user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    entitlements = resolve_entitlements_for_tenant(db, tenant_id)
    limits = entitlements.get("limits", {}) if entitlements else {}
    return get_policies(db, tenant_id, ensure_defaults=True, plan_limits=limits)


@router.patch("/retention/policies", response_model=TenantRetentionPolicyRead)
def update_retention_policy(
    payload: TenantRetentionPolicyUpdate,
    db=Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    entitlements = resolve_entitlements_for_tenant(db, tenant_id)
    try:
        validate_dataset_key(payload.dataset_key)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if payload.is_legal_hold_enabled:
        require_feature(entitlements, "legal_hold", message="Legal hold requires an Enterprise plan")
        if not payload.legal_hold_reason or not payload.legal_hold_reason.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Legal hold reason is required when enabling legal hold.",
            )
    existing = (
        db.query(TenantRetentionPolicy)
        .filter(
            TenantRetentionPolicy.tenant_id == tenant_id,
            TenantRetentionPolicy.dataset_key == payload.dataset_key,
        )
        .first()
    )
    before_retention = existing.retention_days if existing else None
    before_hold = existing.is_legal_hold_enabled if existing else None
    policy = upsert_policy(
        db,
        tenant_id,
        payload.dataset_key,
        retention_days=payload.retention_days,
        is_legal_hold_enabled=payload.is_legal_hold_enabled,
        legal_hold_reason=payload.legal_hold_reason,
        updated_by_user_id=ctx.user_id,
    )
    invalidate_entitlement_cache(tenant_id)
    if before_retention is not None and payload.retention_days is not None:
        if before_retention != policy.retention_days:
            create_audit_log(
                db,
                tenant_id,
                ctx.username,
                f"retention.policy_updated.{policy.dataset_key}",
            )
    if before_hold is not None and payload.is_legal_hold_enabled is not None:
        if before_hold is False and policy.is_legal_hold_enabled:
            create_audit_log(
                db,
                tenant_id,
                ctx.username,
                f"retention.legal_hold_enabled.{policy.dataset_key}",
            )
        elif before_hold is True and not policy.is_legal_hold_enabled:
            create_audit_log(
                db,
                tenant_id,
                ctx.username,
                f"retention.legal_hold_disabled.{policy.dataset_key}",
            )
    return policy
