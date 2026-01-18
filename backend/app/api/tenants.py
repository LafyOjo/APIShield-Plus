from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.core.entitlements import build_tenant_context_snapshot
from app.crud.tenant_settings import get_settings
from app.crud.tenants import create_tenant_with_owner, get_tenant_by_id, list_tenants_for_user
from app.models.enums import MembershipStatusEnum
from app.models.memberships import Membership
from app.models.users import User
from app.schemas.tenants import (
    TenantContextResponse,
    TenantCreate,
    TenantCreateResponse,
    TenantListItem,
)


router = APIRouter(tags=["tenants"])


@router.post("/tenants", response_model=TenantCreateResponse)
def create_tenant_endpoint(
    payload: TenantCreate,
    db=Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        tenant, membership = create_tenant_with_owner(
            db,
            name=payload.name,
            slug=payload.slug,
            owner_user=current_user,
        )
        db.commit()
        db.refresh(tenant)
        db.refresh(membership)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to create tenant") from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to create tenant") from exc

    return {"tenant": tenant, "membership": membership}


@router.get("/tenants", response_model=list[TenantListItem])
def list_tenants_endpoint(
    db=Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = list_tenants_for_user(db, current_user.id)
    return [
        TenantListItem(
            id=tenant.id,
            name=tenant.name,
            slug=tenant.slug,
            role=role,
        )
        for tenant, role in rows
    ]


@router.post("/tenants/{tenant_id}/switch", response_model=TenantContextResponse)
def switch_tenant_endpoint(
    tenant_id: int,
    db=Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tenant = get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    membership = (
        db.query(Membership)
        .filter(
            Membership.tenant_id == tenant_id,
            Membership.user_id == current_user.id,
            Membership.status == MembershipStatusEnum.ACTIVE,
        )
        .first()
    )
    if not membership:
        status_code = status.HTTP_404_NOT_FOUND if settings.TENANT_STRICT_404 else status.HTTP_403_FORBIDDEN
        raise HTTPException(status_code=status_code, detail="Tenant membership not found")

    entitlements = build_tenant_context_snapshot(db, tenant_id)
    settings_snapshot = get_settings(db, tenant_id)
    return {
        "tenant": {
            "id": tenant.id,
            "name": tenant.name,
            "slug": tenant.slug,
            "created_at": tenant.created_at,
        },
        "role": membership.role,
        "entitlements": {
            "features": entitlements["features"],
            "limits": entitlements["limits"],
        },
        "settings": {
            "timezone": settings_snapshot.timezone,
            "retention_days": settings_snapshot.retention_days,
            "alert_prefs": settings_snapshot.alert_prefs,
        },
        "plan_name": entitlements.get("plan_name"),
    }
