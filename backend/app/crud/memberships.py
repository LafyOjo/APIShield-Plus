from sqlalchemy.orm import Session

from app.models.memberships import Membership
from app.models.enums import MembershipStatusEnum, RoleEnum
from app.tenancy.errors import TenantNotFound
from app.tenancy.scoping import get_tenant_owned_or_404, scoped_query


def _normalize_role(role: RoleEnum | str) -> RoleEnum:
    if isinstance(role, RoleEnum):
        return role
    try:
        return RoleEnum(role)
    except ValueError as exc:
        raise ValueError("Invalid role.") from exc


def _normalize_status(status: MembershipStatusEnum | str) -> MembershipStatusEnum:
    if isinstance(status, MembershipStatusEnum):
        return status
    try:
        return MembershipStatusEnum(status)
    except ValueError as exc:
        raise ValueError("Invalid status.") from exc


def count_owners(db: Session, tenant_id: int) -> int:
    return (
        scoped_query(db, Membership, tenant_id)
        .filter(
            Membership.role == RoleEnum.OWNER,
            Membership.status == MembershipStatusEnum.ACTIVE,
        )
        .count()
    )


def assert_can_remove_or_demote_owner(
    db: Session,
    tenant_id: int,
    membership: Membership,
    *,
    new_role: RoleEnum | str | None = None,
) -> None:
    if membership.role != RoleEnum.OWNER or membership.status != MembershipStatusEnum.ACTIVE:
        return
    normalized_role = None
    if new_role is not None:
        normalized_role = _normalize_role(new_role)
        if normalized_role == RoleEnum.OWNER:
            return
    if count_owners(db, tenant_id) <= 1:
        raise ValueError("Cannot remove the last owner from a tenant.")


def create_membership(
    db: Session,
    tenant_id: int,
    user_id: int,
    role: RoleEnum | str,
    created_by_user_id: int | None = None,
    status: MembershipStatusEnum | str = MembershipStatusEnum.ACTIVE,
) -> Membership:
    normalized_role = _normalize_role(role)
    normalized_status = _normalize_status(status)
    if normalized_role != RoleEnum.OWNER and count_owners(db, tenant_id) == 0:
        raise ValueError("Tenant must have at least one owner.")
    membership = (
        scoped_query(db, Membership, tenant_id)
        .filter(Membership.user_id == user_id)
        .first()
    )
    if membership:
        assert_can_remove_or_demote_owner(
            db,
            tenant_id,
            membership,
            new_role=normalized_role,
        )
        membership.role = normalized_role
        membership.status = normalized_status
        db.commit()
        db.refresh(membership)
        return membership
    membership = Membership(
        tenant_id=tenant_id,
        user_id=user_id,
        role=normalized_role,
        status=normalized_status,
        created_by_user_id=created_by_user_id,
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership


def get_membership(db: Session, tenant_id: int, user_id: int) -> Membership:
    membership = (
        scoped_query(db, Membership, tenant_id)
        .filter(Membership.user_id == user_id)
        .first()
    )
    if not membership:
        raise TenantNotFound("Membership not found for tenant")
    return membership


def list_memberships(db: Session, tenant_id: int) -> list[Membership]:
    return scoped_query(db, Membership, tenant_id).order_by(Membership.id).all()


def update_membership_role(
    db: Session,
    tenant_id: int,
    membership_id: int,
    role: RoleEnum | str,
) -> Membership:
    normalized_role = _normalize_role(role)
    membership = get_tenant_owned_or_404(db, Membership, tenant_id, membership_id)
    assert_can_remove_or_demote_owner(
        db,
        tenant_id,
        membership,
        new_role=normalized_role,
    )
    membership.role = normalized_role
    db.commit()
    db.refresh(membership)
    return membership


def remove_membership(db: Session, tenant_id: int, membership_id: int) -> Membership:
    membership = get_tenant_owned_or_404(db, Membership, tenant_id, membership_id)
    assert_can_remove_or_demote_owner(db, tenant_id, membership)
    membership.status = MembershipStatusEnum.SUSPENDED
    db.commit()
    db.refresh(membership)
    return membership
