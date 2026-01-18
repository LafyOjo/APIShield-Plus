from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.core.snippets import build_embed_snippet
from app.crud.api_keys import create_api_key, list_api_keys, revoke_api_key, rotate_api_key
from app.crud.audit import create_audit_log
from app.crud.tenants import get_tenant_by_id, get_tenant_by_slug
from app.crud.website_environments import get_environment
from app.crud.websites import get_website
from app.models.enums import RoleEnum
from app.models.website_environments import WebsiteEnvironment
from app.schemas.api_keys import (
    APIKeyCreate,
    APIKeyCreatedResponse,
    APIKeyCreatedWithSnippetResponse,
    APIKeyCreateRequest,
    APIKeyRead,
    APIKeyRevokeResponse,
)
from app.tenancy.dependencies import require_roles
from app.tenancy.errors import TenantNotFound


router = APIRouter(tags=["api-keys"])


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
    "/websites/{website_id}/environments/{env_id}/keys",
    response_model=APIKeyCreatedResponse,
)
def create_key(
    website_id: int,
    env_id: int,
    payload: APIKeyCreate,
    db=Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    if payload.environment_id != env_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Environment mismatch")
    try:
        get_website(db, tenant_id, website_id)
    except TenantNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Website not found") from exc
    environment = get_environment(db, website_id, env_id)
    if not environment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found")
    api_key, raw_secret = create_api_key(
        db,
        tenant_id=tenant_id,
        website_id=website_id,
        environment_id=env_id,
        name=payload.name,
        created_by_user_id=ctx.user_id,
    )
    return APIKeyCreatedResponse(
        id=api_key.id,
        public_key=api_key.public_key,
        raw_secret=raw_secret if settings.API_KEY_SECRET_RETURN_IN_RESPONSE else None,
    )


@router.get(
    "/websites/{website_id}/keys",
    response_model=list[APIKeyRead],
)
def list_keys(
    website_id: int,
    db=Depends(get_db),
    ctx=Depends(
        require_roles(
            [RoleEnum.OWNER, RoleEnum.ADMIN, RoleEnum.ANALYST, RoleEnum.VIEWER],
            user_resolver=get_current_user,
        )
    ),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    try:
        get_website(db, tenant_id, website_id)
    except TenantNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Website not found") from exc
    return list_api_keys(db, tenant_id, website_id=website_id)


@router.post(
    "/keys/{key_id}/revoke",
    response_model=APIKeyRevokeResponse,
)
def revoke_key(
    key_id: int,
    db=Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    try:
        api_key = revoke_api_key(db, tenant_id, key_id, revoked_by_user_id=ctx.user_id)
    except TenantNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found") from exc
    return APIKeyRevokeResponse(status=api_key.status, revoked_at=api_key.revoked_at)


@router.post(
    "/keys/{key_id}/rotate",
    response_model=APIKeyCreatedResponse,
)
def rotate_key(
    key_id: int,
    db=Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    try:
        api_key, raw_secret = rotate_api_key(db, tenant_id, key_id, created_by_user_id=ctx.user_id)
    except TenantNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found") from exc
    return APIKeyCreatedResponse(
        id=api_key.id,
        public_key=api_key.public_key,
        raw_secret=raw_secret if settings.API_KEY_SECRET_RETURN_IN_RESPONSE else None,
    )


@router.post(
    "/environments/{env_id}/keys",
    response_model=APIKeyCreatedWithSnippetResponse,
)
def create_key_for_environment(
    env_id: int,
    payload: APIKeyCreateRequest,
    request: Request,
    db=Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    environment = db.query(WebsiteEnvironment).filter(WebsiteEnvironment.id == env_id).first()
    if not environment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found")
    try:
        website = get_website(db, tenant_id, environment.website_id)
    except TenantNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found") from exc
    api_key, raw_secret = create_api_key(
        db,
        tenant_id=tenant_id,
        website_id=website.id,
        environment_id=environment.id,
        name=payload.name,
        created_by_user_id=ctx.user_id,
    )
    create_audit_log(
        db,
        tenant_id=tenant_id,
        username=ctx.username,
        event=f"api_key_created:env:{environment.id}:website:{website.id}",
        request=request,
    )
    return APIKeyCreatedWithSnippetResponse(
        id=api_key.id,
        public_key=api_key.public_key,
        created_at=api_key.created_at,
        revoked_at=api_key.revoked_at,
        raw_secret=raw_secret if settings.API_KEY_SECRET_RETURN_IN_RESPONSE else None,
        snippet=build_embed_snippet(api_key.public_key),
    )
