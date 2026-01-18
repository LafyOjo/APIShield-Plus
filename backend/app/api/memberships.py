from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import case

from app.api.dependencies import get_current_user
from app.core.db import get_db
from app.crud.audit import create_audit_log
from app.crud.memberships import list_memberships, remove_membership, update_membership_role
from app.crud.tenants import get_tenant_by_id, get_tenant_by_slug
from app.models.enums import RoleEnum
from app.models.memberships import Membership
from app.models.user_profiles import UserProfile
from app.models.users import User
from app.schemas.memberships import (
    MemberDeleteResponse,
    MemberListItem,
    MemberMembership,
    MemberUser,
    MembershipRead,
    MembershipUpdate,
)
from app.tenancy.dependencies import get_current_membership, require_role_in_tenant, require_roles
from app.tenancy.errors import TenantNotFound
from app.tenancy.scoping import get_tenant_owned_or_404


router = APIRouter(tags=["memberships"])


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


def _format_role(role: RoleEnum) -> str:
    return role.value if hasattr(role, "value") else str(role)


def _get_membership_or_404(db, tenant_id: int, membership_id: int) -> Membership:
    try:
        return get_tenant_owned_or_404(db, Membership, tenant_id, membership_id)
    except TenantNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found") from exc


def _enforce_admin_policy(
    *,
    actor_role: RoleEnum,
    target_membership: Membership,
    new_role: RoleEnum | None = None,
) -> None:
    if actor_role != RoleEnum.ADMIN:
        return
    if target_membership.role == RoleEnum.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins cannot modify owner memberships",
        )
    if new_role == RoleEnum.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins cannot assign owner role",
        )


@router.get("/members", response_model=list[MemberListItem])
def list_members(
    db=Depends(get_db),
    current_user: User = Depends(get_current_user),
    ctx=Depends(require_role_in_tenant([RoleEnum.VIEWER], user_resolver=get_current_user)),
):
    membership = get_current_membership(db, current_user, ctx.tenant_id)
    show_email = ctx.role in {RoleEnum.OWNER, RoleEnum.ADMIN}
    role_order = case(
        (Membership.role == RoleEnum.OWNER, 0),
        (Membership.role == RoleEnum.ADMIN, 1),
        (Membership.role == RoleEnum.ANALYST, 2),
        (Membership.role == RoleEnum.VIEWER, 3),
        else_=4,
    )
    rows = (
        db.query(Membership, User, UserProfile)
        .join(User, User.id == Membership.user_id)
        .outerjoin(UserProfile, UserProfile.user_id == User.id)
        .filter(Membership.tenant_id == membership.tenant_id)
        .order_by(role_order, Membership.created_at.asc())
        .all()
    )
    items: list[MemberListItem] = []
    for member_row, user_row, profile_row in rows:
        items.append(
            MemberListItem(
                user=MemberUser(
                    id=user_row.id,
                    email=user_row.username if show_email else None,
                    display_name=getattr(profile_row, "display_name", None),
                    avatar_url=getattr(profile_row, "avatar_url", None),
                ),
                membership=MemberMembership(
                    id=member_row.id,
                    role=member_row.role,
                    status=member_row.status,
                    created_at=member_row.created_at,
                ),
            )
        )
    return items


@router.get("/memberships", response_model=list[MembershipRead])
def list_memberships_endpoint(
    db=Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    return list_memberships(db, tenant_id)


@router.patch("/memberships/{membership_id}", response_model=MembershipRead)
def update_membership_endpoint(
    membership_id: int,
    payload: MembershipUpdate,
    request: Request,
    db=Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    if payload.role is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role is required")
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    target_membership = _get_membership_or_404(db, tenant_id, membership_id)
    _enforce_admin_policy(actor_role=ctx.role, target_membership=target_membership, new_role=payload.role)
    old_role = target_membership.role
    try:
        membership = update_membership_role(
            db,
            tenant_id=tenant_id,
            membership_id=membership_id,
            role=payload.role,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    create_audit_log(
        db,
        tenant_id=tenant_id,
        username=ctx.username,
        event=f"member_role_changed:{membership.id}:{_format_role(old_role)}->{_format_role(membership.role)}",
        request=request,
    )
    return membership


@router.delete("/memberships/{membership_id}", response_model=MembershipRead)
def remove_membership_endpoint(
    membership_id: int,
    request: Request,
    db=Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    target_membership = _get_membership_or_404(db, tenant_id, membership_id)
    _enforce_admin_policy(actor_role=ctx.role, target_membership=target_membership)
    try:
        membership = remove_membership(db, tenant_id=tenant_id, membership_id=membership_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    create_audit_log(
        db,
        tenant_id=tenant_id,
        username=ctx.username,
        event=f"member_removed:{membership.id}:user:{membership.user_id}",
        request=request,
    )
    return membership


@router.patch("/members/{membership_id}", response_model=MembershipRead)
def update_member_endpoint(
    membership_id: int,
    payload: MembershipUpdate,
    request: Request,
    db=Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    return update_membership_endpoint(membership_id, payload, request, db, ctx)


@router.delete("/members/{membership_id}", response_model=MemberDeleteResponse)
def remove_member_endpoint(
    membership_id: int,
    request: Request,
    db=Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    remove_membership_endpoint(membership_id, request, db, ctx)
    return MemberDeleteResponse(success=True)
