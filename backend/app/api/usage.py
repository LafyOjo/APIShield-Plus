from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_current_user
from app.core.db import get_db
from app.core.usage import get_or_create_current_period_usage
from app.crud.tenants import get_tenant_by_id, get_tenant_by_slug
from app.schemas.tenant_usage import TenantUsageRead
from app.tenancy.dependencies import require_tenant_context


router = APIRouter(tags=["usage"])


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


@router.get("/usage", response_model=TenantUsageRead)
def read_usage(
    db=Depends(get_db),
    ctx=Depends(require_tenant_context(user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    return get_or_create_current_period_usage(tenant_id, db=db)
