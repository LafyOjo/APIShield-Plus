from __future__ import annotations

import secrets
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.scim import verify_scim_token
from app.core.security import get_password_hash
from app.entitlements.enforcement import require_feature
from app.entitlements.resolver import resolve_entitlements_for_tenant
from app.crud.audit import create_audit_log
from app.crud.memberships import (
    assert_can_remove_or_demote_owner,
    count_owners,
    create_membership,
)
from app.crud.scim import (
    ALLOWED_SCIM_ROLES,
    create_scim_user_map,
    get_scim_config,
    get_scim_user_map,
    get_scim_user_map_by_user,
)
from app.crud.tenants import get_tenant_by_id, get_tenant_by_slug
from app.crud.users import create_user, get_user_by_username
from app.models.enums import MembershipStatusEnum, RoleEnum
from app.models.memberships import Membership
from app.models.scim_mappings import SCIMExternalUserMap
from app.core.db import get_db


router = APIRouter(prefix="/scim/v2", tags=["scim"])

SCIM_USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
SCIM_LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"


def _resolve_tenant(db: Session, request: Request):
    header_name = settings.TENANT_HEADER_NAME or "X-Tenant-ID"
    tenant_hint = request.headers.get(header_name)
    if not tenant_hint:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant header required")
    tenant_value = tenant_hint.strip()
    tenant = (
        get_tenant_by_id(db, int(tenant_value))
        if tenant_value.isdigit()
        else get_tenant_by_slug(db, tenant_value)
    )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant


def _require_scim_auth(request: Request, db: Session) -> tuple[int, str]:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing SCIM token")
    token = auth.split("Bearer ")[1].strip()
    tenant = _resolve_tenant(db, request)
    config = get_scim_config(db, tenant.id)
    if not config or not config.is_enabled or not config.scim_token_hash:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="SCIM not enabled")
    entitlements = resolve_entitlements_for_tenant(db, tenant.id)
    require_feature(entitlements, "scim", message="SCIM requires an Enterprise plan")
    if not verify_scim_token(token, config.scim_token_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid SCIM token")
    return tenant.id, tenant.slug


def _ensure_scim_map(
    db: Session,
    *,
    tenant_id: int,
    user_id: int,
    scim_user_id: str | None = None,
) -> SCIMExternalUserMap:
    mapping = get_scim_user_map_by_user(db, tenant_id, user_id)
    if mapping:
        return mapping
    scim_id = scim_user_id or str(uuid4())
    return create_scim_user_map(db, tenant_id, scim_id, user_id)


def _role_from_payload(payload: dict, default_role: RoleEnum) -> RoleEnum:
    role_value = None
    roles = payload.get("roles")
    if isinstance(roles, list) and roles:
        first = roles[0]
        if isinstance(first, dict):
            role_value = first.get("value") or first.get("display")
        elif isinstance(first, str):
            role_value = first
    if role_value is None:
        return default_role
    try:
        role_enum = RoleEnum(role_value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role") from exc
    if role_enum not in ALLOWED_SCIM_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role not allowed for SCIM")
    return role_enum


def _extract_patch(payload: dict) -> tuple[bool | None, RoleEnum | None]:
    active = payload.get("active")
    role = None
    roles = payload.get("roles")
    if isinstance(roles, list) and roles:
        value = roles[0].get("value") if isinstance(roles[0], dict) else roles[0]
        try:
            role = RoleEnum(value)
        except Exception:
            role = None

    for op in payload.get("Operations", []) or []:
        path = (op.get("path") or "").lower()
        value = op.get("value")
        if path.endswith("active") or path == "active":
            active = value
        if "roles" in path:
            if isinstance(value, list) and value:
                first = value[0]
                raw = first.get("value") if isinstance(first, dict) else first
                try:
                    role = RoleEnum(raw)
                except Exception:
                    role = role
        if not path and isinstance(value, dict):
            if "active" in value:
                active = value.get("active")
            if "roles" in value:
                roles_val = value.get("roles")
                if isinstance(roles_val, list) and roles_val:
                    raw = roles_val[0].get("value") if isinstance(roles_val[0], dict) else roles_val[0]
                    try:
                        role = RoleEnum(raw)
                    except Exception:
                        role = role
    return active, role


def _scim_user_response(scim_id: str, user, membership: Membership) -> dict:
    role_value = membership.role.value if hasattr(membership.role, "value") else str(membership.role)
    active = membership.status == MembershipStatusEnum.ACTIVE
    return {
        "schemas": [SCIM_USER_SCHEMA],
        "id": scim_id,
        "userName": user.username,
        "active": active,
        "displayName": getattr(user, "display_name", None),
        "emails": [{"value": user.username, "primary": True}],
        "roles": [{"value": role_value}],
        "meta": {"resourceType": "User"},
    }


@router.get("/Users")
def list_scim_users(
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id, _tenant_slug = _require_scim_auth(request, db)
    memberships = (
        db.query(Membership)
        .filter(Membership.tenant_id == tenant_id)
        .order_by(Membership.id.asc())
        .all()
    )
    resources = []
    for membership in memberships:
        user = membership.user
        mapping = _ensure_scim_map(db, tenant_id=tenant_id, user_id=user.id)
        resources.append(_scim_user_response(mapping.scim_user_id, user, membership))

    return {
        "schemas": [SCIM_LIST_SCHEMA],
        "totalResults": len(resources),
        "startIndex": 1,
        "itemsPerPage": len(resources),
        "Resources": resources,
    }


@router.post("/Users")
def create_scim_user(
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id, _tenant_slug = _require_scim_auth(request, db)
    config = get_scim_config(db, tenant_id)
    if not config:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="SCIM not enabled")

    user_name = payload.get("userName")
    if not user_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="userName required")
    normalized_username = user_name.strip().lower()

    user = get_user_by_username(db, normalized_username)
    if not user:
        random_password = secrets.token_urlsafe(16)
        user = create_user(
            db,
            username=normalized_username,
            password_hash=get_password_hash(random_password),
            role="user",
        )

    try:
        default_role = RoleEnum(config.default_role)
    except Exception:
        default_role = RoleEnum.VIEWER
    role = _role_from_payload(payload, default_role)
    if role not in ALLOWED_SCIM_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role not allowed for SCIM")

    active = payload.get("active")
    status_value = MembershipStatusEnum.ACTIVE
    if active is False:
        status_value = MembershipStatusEnum.SUSPENDED

    membership = (
        db.query(Membership)
        .filter(Membership.tenant_id == tenant_id, Membership.user_id == user.id)
        .first()
    )
    if membership:
        if role != membership.role:
            assert_can_remove_or_demote_owner(db, tenant_id, membership, new_role=role)
            membership.role = role
        membership.status = status_value
        db.commit()
        db.refresh(membership)
    else:
        membership = create_membership(
            db,
            tenant_id=tenant_id,
            user_id=user.id,
            role=role,
            status=status_value,
        )

    scim_id = payload.get("id")
    if not scim_id:
        scim_id = str(uuid4())
    mapping = _ensure_scim_map(db, tenant_id=tenant_id, user_id=user.id, scim_user_id=scim_id)

    create_audit_log(
        db,
        tenant_id=tenant_id,
        username="scim",
        event=f"scim_user_provisioned:{user.username}",
        request=request,
    )
    return _scim_user_response(mapping.scim_user_id, user, membership)


@router.get("/Users/{scim_user_id}")
def get_scim_user(
    scim_user_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id, _tenant_slug = _require_scim_auth(request, db)
    mapping = get_scim_user_map(db, tenant_id, scim_user_id)
    if not mapping:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    membership = (
        db.query(Membership)
        .filter(Membership.tenant_id == tenant_id, Membership.user_id == mapping.user_id)
        .first()
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user = membership.user
    return _scim_user_response(mapping.scim_user_id, user, membership)


@router.patch("/Users/{scim_user_id}")
def patch_scim_user(
    scim_user_id: str,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id, _tenant_slug = _require_scim_auth(request, db)
    mapping = get_scim_user_map(db, tenant_id, scim_user_id)
    if not mapping:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    membership = (
        db.query(Membership)
        .filter(Membership.tenant_id == tenant_id, Membership.user_id == mapping.user_id)
        .first()
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    active, role = _extract_patch(payload)

    if role is not None:
        if role not in ALLOWED_SCIM_ROLES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role not allowed for SCIM")
        assert_can_remove_or_demote_owner(db, tenant_id, membership, new_role=role)
        membership.role = role
        create_audit_log(
            db,
            tenant_id=tenant_id,
            username="scim",
            event=f"scim_role_changed:{membership.user.username}:{role.value}",
            request=request,
        )

    if active is not None:
        if active is False:
            if membership.role == RoleEnum.OWNER and count_owners(db, tenant_id) <= 1:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot deactivate last owner")
            membership.status = MembershipStatusEnum.SUSPENDED
            create_audit_log(
                db,
                tenant_id=tenant_id,
                username="scim",
                event=f"scim_user_deprovisioned:{membership.user.username}",
                request=request,
            )
        else:
            membership.status = MembershipStatusEnum.ACTIVE
    db.commit()
    db.refresh(membership)
    return _scim_user_response(mapping.scim_user_id, membership.user, membership)


@router.delete("/Users/{scim_user_id}")
def delete_scim_user(
    scim_user_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant_id, _tenant_slug = _require_scim_auth(request, db)
    mapping = get_scim_user_map(db, tenant_id, scim_user_id)
    if not mapping:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    membership = (
        db.query(Membership)
        .filter(Membership.tenant_id == tenant_id, Membership.user_id == mapping.user_id)
        .first()
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if membership.role == RoleEnum.OWNER and count_owners(db, tenant_id) <= 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot deactivate last owner")
    membership.status = MembershipStatusEnum.SUSPENDED
    db.commit()
    db.refresh(membership)
    create_audit_log(
        db,
        tenant_id=tenant_id,
        username="scim",
        event=f"scim_user_deprovisioned:{membership.user.username}",
        request=request,
    )
    return {"status": "disabled"}
