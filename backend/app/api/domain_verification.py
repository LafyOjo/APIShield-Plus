from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.core.verification import build_verification_instructions, validate_verification_method
from app.crud.domain_verification import (
    create_verification,
    get_latest_verification,
    update_check_status,
)
from app.crud.tenants import get_tenant_by_id, get_tenant_by_slug
from app.crud.websites import get_website
from app.models.enums import RoleEnum
from app.schemas.domain_verification import (
    DomainVerificationCheckRequest,
    DomainVerificationStartRequest,
    DomainVerificationStartResponse,
    DomainVerificationStatus,
)
from app.tenancy.dependencies import require_roles, require_tenant_context
from app.tenancy.errors import TenantNotFound


router = APIRouter(tags=["domain-verification"])


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


@router.post(
    "/websites/{website_id}/verify/start",
    response_model=DomainVerificationStartResponse,
)
def start_verification(
    website_id: int,
    payload: DomainVerificationStartRequest,
    db=Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    try:
        website = get_website(db, tenant_id, website_id)
    except TenantNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Website not found") from exc
    try:
        validate_verification_method(payload.method)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    verification = create_verification(
        db,
        tenant_id,
        website_id,
        payload.method,
        created_by_user_id=ctx.user_id,
    )
    instructions = build_verification_instructions(website.domain, verification.token, payload.method)
    return DomainVerificationStartResponse(
        id=verification.id,
        method=verification.method,
        token=verification.token,
        status=verification.status,
        instructions=instructions,
    )


@router.post(
    "/websites/{website_id}/verify/check",
    response_model=DomainVerificationStatus,
)
def check_verification(
    website_id: int,
    payload: DomainVerificationCheckRequest,
    db=Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    try:
        website = get_website(db, tenant_id, website_id)
    except TenantNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Website not found") from exc
    try:
        verification = get_latest_verification(
            db,
            tenant_id=tenant_id,
            website_id=website_id,
            method=payload.method,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not verification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Verification not found")
    if payload.force_verify and not settings.ALLOW_MULTI_TENANT_DEV_BYPASS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Manual verification not allowed")
    updated = update_check_status(db, verification, verified=payload.force_verify or None)
    return updated


@router.get(
    "/websites/{website_id}/verify/status",
    response_model=DomainVerificationStatus,
)
def verification_status(
    website_id: int,
    db=Depends(get_db),
    ctx=Depends(require_tenant_context(user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    try:
        website = get_website(db, tenant_id, website_id)
    except TenantNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Website not found") from exc
    verification = get_latest_verification(db, tenant_id, website_id)
    if not verification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Verification not found")
    return verification
