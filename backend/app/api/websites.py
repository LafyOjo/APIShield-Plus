from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import get_current_user
from app.core.db import get_db
from app.core.snippets import build_embed_snippet
from app.core.verification import build_verification_instructions
from app.crud.api_keys import list_api_keys
from app.crud.audit import create_audit_log
from app.crud.domain_verification import get_latest_verification
from app.crud.website_environments import create_environment, list_environments
from app.crud.websites import create_website, get_website, list_websites
from app.models.enums import RoleEnum
from app.schemas.website_environments import WebsiteEnvironmentCreate, WebsiteEnvironmentRead
from app.schemas.website_stack_profiles import WebsiteStackProfileRead, WebsiteStackProfileUpdate
from app.schemas.websites import (
    WebsiteCreate,
    WebsiteInstallEnvironment,
    WebsiteInstallKey,
    WebsiteInstallRead,
    WebsiteInstallVerification,
    WebsiteRead,
)
from app.tenancy.dependencies import get_current_membership, require_role_in_tenant
from app.tenancy.errors import TenantNotFound
from app.crud.website_stack_profiles import (
    clear_stack_manual_override,
    get_or_create_stack_profile,
    set_stack_manual_override,
)
from app.stack.constants import STACK_TYPES


router = APIRouter(tags=["websites"])


@router.post("/websites", response_model=WebsiteRead)
def create_website_endpoint(
    payload: WebsiteCreate,
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    ctx=Depends(require_role_in_tenant([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    membership = get_current_membership(db, current_user, ctx.tenant_id)
    try:
        website = create_website(
            db,
            tenant_id=membership.tenant_id,
            domain=payload.domain,
            display_name=payload.display_name,
            created_by_user_id=ctx.user_id,
        )
    except ValueError as exc:
        message = str(exc)
        status_code = (
            status.HTTP_409_CONFLICT
            if "already exists" in message.lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=status_code, detail=message) from exc
    create_audit_log(
        db,
        tenant_id=membership.tenant_id,
        username=ctx.username,
        event=f"website_created:{website.domain}",
        request=request,
    )
    return website


@router.get("/websites", response_model=list[WebsiteRead])
def list_websites_endpoint(
    include_deleted: bool = False,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    ctx=Depends(require_role_in_tenant([RoleEnum.VIEWER], user_resolver=get_current_user)),
):
    membership = get_current_membership(db, current_user, ctx.tenant_id)
    if include_deleted and ctx.role not in {RoleEnum.OWNER, RoleEnum.ADMIN}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role for deleted websites")
    return list_websites(db, membership.tenant_id, include_deleted=include_deleted)


@router.get("/websites/{website_id}", response_model=WebsiteRead)
def get_website_endpoint(
    website_id: int,
    include_deleted: bool = False,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    ctx=Depends(require_role_in_tenant([RoleEnum.VIEWER], user_resolver=get_current_user)),
):
    membership = get_current_membership(db, current_user, ctx.tenant_id)
    if include_deleted and ctx.role not in {RoleEnum.OWNER, RoleEnum.ADMIN}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role for deleted websites")
    try:
        return get_website(db, membership.tenant_id, website_id, include_deleted=include_deleted)
    except TenantNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Website not found") from exc


def _build_next_steps(
    *,
    has_keys: bool,
    verification: WebsiteInstallVerification | None,
) -> list[str]:
    steps: list[str] = []
    if not has_keys:
        steps.append("Create an API key for your environment")
    else:
        steps.append("Embed the snippet in your site")
    if not verification or verification.status != "verified":
        steps.append("Verify domain ownership")
    return steps


@router.get("/websites/{website_id}/install", response_model=WebsiteInstallRead)
def get_install_instructions(
    website_id: int,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    ctx=Depends(require_role_in_tenant([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    membership = get_current_membership(db, current_user, ctx.tenant_id)
    try:
        website = get_website(db, membership.tenant_id, website_id)
    except TenantNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Website not found") from exc

    environments = list_environments(db, website.id)
    env_payloads: list[WebsiteInstallEnvironment] = []
    has_keys = False
    for env in environments:
        keys = list_api_keys(db, membership.tenant_id, environment_id=env.id)
        key_payloads: list[WebsiteInstallKey] = []
        for key in keys:
            has_keys = True
            key_payloads.append(
                WebsiteInstallKey(
                    id=key.id,
                    name=key.name,
                    public_key=key.public_key,
                    created_at=key.created_at,
                    revoked_at=key.revoked_at,
                    status=key.status,
                    snippet=build_embed_snippet(key.public_key),
                )
            )
        env_payloads.append(
            WebsiteInstallEnvironment(
                id=env.id,
                name=env.name,
                base_url=env.base_url,
                status=env.status,
                keys=key_payloads,
            )
        )

    verification = get_latest_verification(db, membership.tenant_id, website.id)
    verification_payload = None
    if verification:
        verification_payload = WebsiteInstallVerification(
            id=verification.id,
            method=verification.method,
            status=verification.status,
            created_at=verification.created_at,
            verified_at=verification.verified_at,
            last_checked_at=verification.last_checked_at,
            token=verification.token,
            instructions=build_verification_instructions(
                website.domain,
                verification.token,
                verification.method,
            ),
        )

    website_payload = WebsiteRead(
        id=website.id,
        domain=website.domain,
        display_name=website.display_name,
        status=website.status,
        created_at=website.created_at,
    )

    return WebsiteInstallRead(
        website=website_payload,
        environments=env_payloads,
        verification=verification_payload,
        next_steps=_build_next_steps(has_keys=has_keys, verification=verification_payload),
    )


@router.post(
    "/websites/{website_id}/environments",
    response_model=WebsiteEnvironmentRead,
)
def create_environment_endpoint(
    website_id: int,
    payload: WebsiteEnvironmentCreate,
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    ctx=Depends(require_role_in_tenant([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    membership = get_current_membership(db, current_user, ctx.tenant_id)
    try:
        website = get_website(db, membership.tenant_id, website_id)
    except TenantNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Website not found") from exc

    env_name = payload.name.strip().lower()
    if env_name != "staging":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only the staging environment can be created in v1",
        )
    try:
        environment = create_environment(
            db,
            website_id=website.id,
            name=env_name,
            base_url=payload.base_url,
        )
    except ValueError as exc:
        message = str(exc)
        status_code = (
            status.HTTP_409_CONFLICT
            if "already exists" in message.lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=status_code, detail=message) from exc

    create_audit_log(
        db,
        tenant_id=membership.tenant_id,
        username=ctx.username,
        event=f"environment_created:{website.domain}:{environment.name}",
        request=request,
    )
    return environment


@router.get("/websites/{website_id}/stack", response_model=WebsiteStackProfileRead)
def get_stack_profile_endpoint(
    website_id: int,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    ctx=Depends(require_role_in_tenant([RoleEnum.VIEWER], user_resolver=get_current_user)),
):
    membership = get_current_membership(db, current_user, ctx.tenant_id)
    try:
        website = get_website(db, membership.tenant_id, website_id)
    except TenantNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Website not found") from exc

    profile = get_or_create_stack_profile(
        db,
        tenant_id=membership.tenant_id,
        website_id=website.id,
    )
    return profile


@router.patch("/websites/{website_id}/stack", response_model=WebsiteStackProfileRead)
def update_stack_profile_endpoint(
    website_id: int,
    payload: WebsiteStackProfileUpdate,
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    ctx=Depends(require_role_in_tenant([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    membership = get_current_membership(db, current_user, ctx.tenant_id)
    try:
        website = get_website(db, membership.tenant_id, website_id)
    except TenantNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Website not found") from exc

    changes = payload.dict(exclude_unset=True)
    if not changes:
        profile = get_or_create_stack_profile(
            db,
            tenant_id=membership.tenant_id,
            website_id=website.id,
        )
        return profile

    if changes.get("stack_type"):
        stack_type = changes["stack_type"]
        if stack_type not in STACK_TYPES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid stack type")
        profile = set_stack_manual_override(
            db,
            tenant_id=membership.tenant_id,
            website_id=website.id,
            stack_type=stack_type,
        )
        create_audit_log(
            db,
            tenant_id=membership.tenant_id,
            username=ctx.username,
            event=f"website_stack_override:{website.domain}:{stack_type}",
            request=request,
        )
        return profile

    if changes.get("manual_override") is False:
        profile = clear_stack_manual_override(
            db,
            tenant_id=membership.tenant_id,
            website_id=website.id,
        )
        create_audit_log(
            db,
            tenant_id=membership.tenant_id,
            username=ctx.username,
            event=f"website_stack_override_cleared:{website.domain}",
            request=request,
        )
        return profile

    profile = get_or_create_stack_profile(
        db,
        tenant_id=membership.tenant_id,
        website_id=website.id,
    )
    return profile
