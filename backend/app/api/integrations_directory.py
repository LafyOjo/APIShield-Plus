from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import get_current_user
from app.core.db import get_db
from app.crud.integration_directory import (
    create_install_event,
    list_listings,
    serialize_listing,
)
from app.crud.websites import get_website
from app.crud.website_stack_profiles import get_or_create_stack_profile
from app.schemas.integration_directory import (
    IntegrationInstallEventCreate,
    IntegrationInstallEventRead,
    IntegrationListingRead,
)
from app.tenancy.dependencies import get_current_membership, require_role_in_tenant
from app.tenancy.errors import TenantNotFound


router = APIRouter(tags=["integrations-directory"])
public_router = APIRouter(tags=["integrations-directory"])


def _apply_recommendations(listings: list[dict], stack_type: str | None) -> list[dict]:
    if not stack_type:
        for item in listings:
            item["recommended"] = False
        return listings
    normalized = stack_type.strip().lower()
    for item in listings:
        stack_types = [str(v).lower() for v in (item.get("stack_types") or [])]
        item["recommended"] = normalized in stack_types if stack_types else False
    return listings


@public_router.get("/public/integrations", response_model=list[IntegrationListingRead])
def list_public_integrations(
    db=Depends(get_db),
):
    listings = [serialize_listing(item) for item in list_listings(db)]
    listings = _apply_recommendations(listings, None)
    return listings


@router.get("/integrations/directory", response_model=list[IntegrationListingRead])
def list_integrations_directory(
    request: Request,
    website_id: int | None = None,
    recommended_only: bool = False,
    category: str | None = None,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    ctx=Depends(require_role_in_tenant(["viewer"], user_resolver=get_current_user)),
):
    membership = get_current_membership(db, current_user, ctx.tenant_id)
    listings = [serialize_listing(item) for item in list_listings(db)]

    stack_type = None
    if website_id is not None:
        try:
            get_website(db, membership.tenant_id, website_id)
        except TenantNotFound as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Website not found") from exc
        profile = get_or_create_stack_profile(db, tenant_id=membership.tenant_id, website_id=website_id)
        stack_type = profile.stack_type

    listings = _apply_recommendations(listings, stack_type)
    if recommended_only:
        listings = [item for item in listings if item.get("recommended")]
    if category:
        listings = [item for item in listings if item.get("category") == category]
    return listings


@router.post("/integrations/install-events", response_model=IntegrationInstallEventRead)
def log_integration_install_event(
    payload: IntegrationInstallEventCreate,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    ctx=Depends(require_role_in_tenant(["viewer"], user_resolver=get_current_user)),
):
    membership = get_current_membership(db, current_user, ctx.tenant_id)
    try:
        event = create_install_event(
            db,
            tenant_id=membership.tenant_id,
            integration_key=payload.integration_key,
            website_id=payload.website_id,
            method=payload.method,
            metadata=payload.metadata,
        )
    except ValueError as exc:
        message = str(exc)
        status_code = status.HTTP_404_NOT_FOUND if "not found" in message.lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=message) from exc
    return event
