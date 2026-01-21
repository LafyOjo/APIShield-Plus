from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.core.entitlements import build_tenant_context_snapshot
from app.crud.tenant_settings import get_settings
from app.models.memberships import Membership
from app.models.tenants import Tenant
from app.models.users import User
from app.schemas.me import (
    EntitlementsSnapshot,
    MeMembership,
    MeResponse,
    MeTenant,
    MeUser,
)
from app.tenancy.constants import TENANT_HEADER
from app.tenancy.dependencies import get_current_membership


router = APIRouter(tags=["me"])


def _resolve_active_tenant_header(request: Request) -> Optional[str]:
    header_name = settings.TENANT_HEADER_NAME or TENANT_HEADER
    tenant_hint = request.headers.get(header_name)
    return tenant_hint.strip() if tenant_hint else None


@router.get("/me", response_model=MeResponse)
def read_me(
    request: Request,
    db=Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(Membership, Tenant)
        .join(Tenant, Membership.tenant_id == Tenant.id)
        .filter(
            Membership.user_id == current_user.id,
            Tenant.deleted_at.is_(None),
        )
        .order_by(Tenant.name.asc())
        .all()
    )
    memberships = [
        MeMembership(
            tenant=MeTenant(id=tenant.id, name=tenant.name, slug=tenant.slug),
            role=membership.role,
            status=membership.status,
        )
        for membership, tenant in rows
    ]
    user = MeUser(
        id=current_user.id,
        username=current_user.username,
        display_name=getattr(current_user, "display_name", None),
    )
    active_tenant_hint = _resolve_active_tenant_header(request)
    if active_tenant_hint:
        membership = get_current_membership(db, current_user, active_tenant_hint)
        tenant = db.query(Tenant).filter(Tenant.id == membership.tenant_id).first()
        if not tenant:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
        entitlements = build_tenant_context_snapshot(db, tenant.id)
        settings_snapshot = get_settings(db, tenant.id)
        settings_payload = {
            "timezone": settings_snapshot.timezone,
            "retention_days": settings_snapshot.retention_days,
            "event_retention_days": settings_snapshot.event_retention_days,
            "ip_raw_retention_days": settings_snapshot.ip_raw_retention_days,
            "default_revenue_per_conversion": settings_snapshot.default_revenue_per_conversion,
            "alert_prefs": settings_snapshot.alert_prefs,
        }
        return MeResponse(
            user=user,
            memberships=memberships,
            active_tenant=MeTenant(id=tenant.id, name=tenant.name, slug=tenant.slug),
            active_role=membership.role,
            entitlements=EntitlementsSnapshot(
                features=entitlements["features"],
                limits=entitlements["limits"],
            ),
            settings=settings_payload,
        )
    return MeResponse(user=user, memberships=memberships)
