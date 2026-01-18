from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_current_user
from app.core.db import get_db
from app.core.email import send_invite_email
from app.crud.invites import accept_invite, create_invite, get_pending_invites
from app.crud.tenants import get_tenant_by_id, get_tenant_by_slug
from app.models.enums import RoleEnum
from app.schemas.invites import InviteAcceptRequest, InviteCreate, InviteCreatedResponse, InviteRead
from app.schemas.memberships import MembershipRead
from app.tenancy.dependencies import require_roles


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
    db=Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    invite, raw_token = create_invite(
        db,
        tenant_id=tenant_id,
        email=payload.email,
        role=payload.role,
        created_by_user_id=ctx.user_id,
    )
    send_invite_email(invite.email, raw_token)
    return InviteCreatedResponse(
        id=invite.id,
        email=invite.email,
        role=invite.role,
        expires_at=invite.expires_at,
        token=raw_token,
    )


@router.get("/invites", response_model=list[InviteRead])
def list_invites_endpoint(
    db=Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    return get_pending_invites(db, tenant_id)


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
