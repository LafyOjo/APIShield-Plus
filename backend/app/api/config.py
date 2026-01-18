# This small API file exposes read-only configuration details
# to the frontend/dashboard. For now it only shares the
# "fail_limit" setting (how many failed login attempts are
# allowed before rate limiting / lockout kicks in).
#
# Only owners/admins can call this endpoint, to prevent regular users
# from learning security policy details like thresholds.

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.crud.tenant_settings import get_settings
from app.crud.tenants import get_tenant_by_id, get_tenant_by_slug
from app.models.enums import RoleEnum
from app.tenancy.dependencies import require_roles

# Router setup - all endpoints here tagged as "config"
router = APIRouter(tags=["config"])


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


# Returns the currently active fail_limit value.
# This now reads from tenant settings, with settings.FAIL_LIMIT
# used as a fallback default. The require_roles dependency
# enforces tenant context + admin role (pattern for tenant-aware routes).
@router.get("/config")
def get_config(
    db=Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    """Return the current FAIL_LIMIT configuration value."""
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    tenant_settings = get_settings(db, tenant_id)
    alert_prefs = tenant_settings.alert_prefs or {}
    fail_limit = alert_prefs.get("fail_limit", settings.FAIL_LIMIT)
    return {"fail_limit": fail_limit}
