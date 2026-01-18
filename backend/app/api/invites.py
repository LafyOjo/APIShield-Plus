from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.core.email import send_invite_email
from app.crud.audit import create_audit_log
from app.crud.invites import accept_invite, create_invite, get_pending_invites
from app.crud.tenants import get_tenant_by_id, get_tenant_by_slug
from app.crud.users import get_user_by_username
from app.models.enums import MembershipStatusEnum, RoleEnum
from app.models.memberships import Membership
from app.schemas.invites import InviteAcceptRequest, InviteCreate, InviteCreatedResponse, InviteRead
from app.schemas.memberships import MembershipRead
from app.tenancy.dependencies import require_role_in_tenant


router = APIRouter(tags=["invites"])


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


@router.post("/invites", response_model=InviteCreatedResponse)
def create_invite_endpoint(
    payload: InviteCreate,
    request: Request,
    db=Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    existing_user = get_user_by_username(db, payload.email)
    if existing_user:
        existing_membership = (
            db.query(Membership)
            .filter(
                Membership.tenant_id == tenant_id,
                Membership.user_id == existing_user.id,
                Membership.status == MembershipStatusEnum.ACTIVE,
            )
            .first()
        )
        if existing_membership:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User already belongs to this tenant",
            )
    invite, raw_token = create_invite(
        db,
        tenant_id=tenant_id,
        email=payload.email,
        role=payload.role,
        created_by_user_id=ctx.user_id,
    )
    create_audit_log(
        db,
        tenant_id=tenant_id,
        username=ctx.username,
        event=f"invite_created:{invite.email}",
        request=request,
    )
    send_invite_email(invite.email, raw_token)
    return InviteCreatedResponse(
        id=invite.id,
        email=invite.email,
        role=invite.role,
        expires_at=invite.expires_at,
        token=raw_token if settings.INVITE_TOKEN_RETURN_IN_RESPONSE else None,
    )


@router.get("/invites", response_model=list[InviteRead])
def list_invites_endpoint(
    include_expired: bool = False,
    db=Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    return get_pending_invites(db, tenant_id, include_expired=include_expired)


@router.post("/invites/accept", response_model=MembershipRead)
def accept_invite_endpoint(
    payload: InviteAcceptRequest,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    membership = accept_invite(db, payload.token, current_user.id)
    if not membership:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired invite")
    return membership
