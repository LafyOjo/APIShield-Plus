from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import utcnow
from app.core.tokens import generate_token, hash_token, verify_token
from app.crud.memberships import create_membership
from app.models.enums import MembershipStatusEnum, RoleEnum
from app.models.invites import Invite
from app.tenancy.scoping import scoped_query
from app.models.memberships import Membership


def _naive_utcnow():
    now = utcnow()
    if now.tzinfo is None:
        return now
    return now.replace(tzinfo=None)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _normalize_role(role: RoleEnum | str) -> RoleEnum:
    if isinstance(role, RoleEnum):
        return role
    try:
        return RoleEnum(role)
    except ValueError as exc:
        raise ValueError("Invalid role.") from exc


def _format_invite_token(invite_id: int, secret: str) -> str:
    return f"inv_{invite_id}_{secret}"


def _parse_invite_token(token: str) -> tuple[int | None, str | None]:
    if not token or not token.startswith("inv_"):
        return None, None
    parts = token.split("_", 2)
    if len(parts) != 3:
        return None, None
    _, invite_id, secret = parts
    if not invite_id.isdigit() or not secret:
        return None, None
    return int(invite_id), secret


def create_invite(
    db: Session,
    tenant_id: int,
    email: str,
    role: RoleEnum | str,
    created_by_user_id: int,
    ttl_hours: int | None = None,
) -> tuple[Invite, str]:
    normalized_role = _normalize_role(role)
    ttl_hours = ttl_hours if ttl_hours is not None else settings.INVITE_TOKEN_TTL_HOURS
    if ttl_hours <= 0:
        raise ValueError("Invite TTL must be positive.")
    secret = generate_token()
    token_hash = hash_token(secret)
    expires_at = _naive_utcnow() + timedelta(hours=ttl_hours)
    invite = Invite(
        tenant_id=tenant_id,
        email=_normalize_email(email),
        role=normalized_role,
        token_hash=token_hash,
        expires_at=expires_at,
        created_by_user_id=created_by_user_id,
    )
    db.add(invite)
    db.flush()
    raw_token = _format_invite_token(invite.id, secret)
    db.commit()
    db.refresh(invite)
    return invite, raw_token


def get_pending_invites(
    db: Session,
    tenant_id: int,
    *,
    include_expired: bool = False,
) -> list[Invite]:
    query = scoped_query(db, Invite, tenant_id).filter(Invite.accepted_at.is_(None))
    if not include_expired:
        query = query.filter(Invite.expires_at > _naive_utcnow())
    return query.order_by(Invite.created_at.desc()).all()


def list_pending_invites(
    db: Session,
    tenant_id: int,
    *,
    include_expired: bool = False,
) -> list[Invite]:
    return get_pending_invites(db, tenant_id, include_expired=include_expired)


def get_invite_by_token(db: Session, token: str) -> Invite | None:
    invite_id, secret = _parse_invite_token(token)
    if invite_id is None or secret is None:
        return None
    invite = db.query(Invite).filter(Invite.id == invite_id).first()
    if not invite:
        return None
    if not verify_token(secret, invite.token_hash):
        return None
    return invite


def accept_invite(db: Session, token: str, user_id: int) -> Membership | None:
    invite = get_invite_by_token(db, token)
    if not invite:
        return None
    now = _naive_utcnow()
    if invite.accepted_at is not None or invite.expires_at <= now:
        return None
    try:
        membership = create_membership(
            db,
            tenant_id=invite.tenant_id,
            user_id=user_id,
            role=invite.role,
            created_by_user_id=invite.created_by_user_id,
            status=MembershipStatusEnum.ACTIVE,
        )
    except ValueError:
        return None
    invite.accepted_at = now
    db.commit()
    db.refresh(invite)
    return membership


def revoke_invite(db: Session, tenant_id: int, invite_id: int) -> Invite | None:
    invite = (
        scoped_query(db, Invite, tenant_id)
        .filter(Invite.id == invite_id)
        .first()
    )
    if not invite:
        return None
    invite.expires_at = _naive_utcnow()
    db.commit()
    db.refresh(invite)
    return invite
