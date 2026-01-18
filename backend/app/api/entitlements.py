from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_current_user
from app.core.db import get_db
from app.core.entitlements import get_effective_entitlements
from app.crud.tenants import get_tenant_by_id, get_tenant_by_slug
from app.schemas.feature_entitlements import FeatureEntitlementRead
from app.tenancy.dependencies import require_tenant_context


router = APIRouter(tags=["entitlements"])


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


@router.get("/entitlements", response_model=list[FeatureEntitlementRead])
def list_entitlements(
    db=Depends(get_db),
    ctx=Depends(require_tenant_context(user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    return get_effective_entitlements(db, tenant_id)
