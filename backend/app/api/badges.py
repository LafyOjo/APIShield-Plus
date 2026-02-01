from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import get_current_user
from app.core.badges import apply_badge_policy_to_payload, serialize_badge_config
from app.core.config import settings
from app.core.db import get_db
from app.crud.audit import create_audit_log
from app.crud.trust_badges import get_or_create_badge_config, upsert_badge_config
from app.crud.websites import get_website
from app.entitlements.resolver import resolve_entitlements_for_tenant
from app.models.enums import RoleEnum
from app.schemas.trust_badges import TrustBadgeConfigRead, TrustBadgeConfigUpdate
from app.tenancy.dependencies import get_current_membership, require_role_in_tenant
from app.tenancy.errors import TenantNotFound


router = APIRouter(tags=["badges"])


def _build_script_url(request: Request, website_id: int) -> str:
    base_url = (settings.APP_BASE_URL or str(request.base_url)).rstrip("/")
    return f"{base_url}/public/badge.js?website_id={website_id}"


def _build_script_tag(script_url: str) -> str:
    return f'<script async src="{script_url}"></script>'


def _response_payload(
    config,
    *,
    plan_key: str | None,
    request: Request,
) -> TrustBadgeConfigRead:
    payload = serialize_badge_config(config)
    payload = apply_badge_policy_to_payload(payload, plan_key)
    script_url = _build_script_url(request, payload["website_id"])
    payload["script_url"] = script_url
    payload["script_tag"] = _build_script_tag(script_url)
    return TrustBadgeConfigRead(**payload)


@router.get("/badges/config", response_model=TrustBadgeConfigRead)
def get_badge_config_endpoint(
    website_id: int,
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    ctx=Depends(require_role_in_tenant([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    membership = get_current_membership(db, current_user, ctx.tenant_id)
    try:
        get_website(db, membership.tenant_id, website_id)
    except TenantNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Website not found") from exc

    config = get_or_create_badge_config(db, membership.tenant_id, website_id)
    entitlements = resolve_entitlements_for_tenant(db, membership.tenant_id)
    return _response_payload(config, plan_key=entitlements.get("plan_key"), request=request)


@router.post("/badges/config", response_model=TrustBadgeConfigRead)
def upsert_badge_config_endpoint(
    payload: TrustBadgeConfigUpdate,
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    ctx=Depends(require_role_in_tenant([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    membership = get_current_membership(db, current_user, ctx.tenant_id)
    try:
        get_website(db, membership.tenant_id, payload.website_id)
    except TenantNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Website not found") from exc

    updates = payload.dict(exclude_unset=True)
    website_id = updates.pop("website_id")
    entitlements = resolve_entitlements_for_tenant(db, membership.tenant_id)
    config = upsert_badge_config(
        db,
        tenant_id=membership.tenant_id,
        website_id=website_id,
        updates=updates,
        plan_key=entitlements.get("plan_key"),
    )
    create_audit_log(
        db,
        tenant_id=membership.tenant_id,
        username=ctx.username,
        event=f"trust_badge_config_updated:{website_id}",
        request=request,
    )
    return _response_payload(config, plan_key=entitlements.get("plan_key"), request=request)
