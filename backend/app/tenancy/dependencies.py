"""
FastAPI dependency helpers for tenant context and RBAC.
"""

from typing import Callable, Iterable, Optional
from uuid import uuid4

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.models.enums import MembershipStatusEnum, RoleEnum
from app.tenancy.constants import TENANT_HEADER
from app.tenancy.context import RequestContext
from app.crud.tenants import get_tenant_by_id, get_tenant_by_slug
from app.models.memberships import Membership


def _resolve_tenant_id(request: Request) -> Optional[str]:
    tenant_header = settings.TENANT_HEADER_NAME or TENANT_HEADER
    tenant_id = request.headers.get(tenant_header) if request else None
    if tenant_id:
        return tenant_id
    support_tenant = getattr(getattr(request, "state", None), "support_tenant_id", None)
    if support_tenant:
        return str(support_tenant)
    if settings.DEFAULT_TENANT_SLUG:
        return settings.DEFAULT_TENANT_SLUG
    return None


def _resolve_membership_role(db: Session, user, tenant_id: Optional[str]) -> Optional[RoleEnum]:
    """
    Resolve the caller's role from the membership table.
    """
    if user is None or tenant_id is None or db is None:
        return None
    if getattr(user, "support_mode", False):
        support_tenant_id = getattr(user, "support_tenant_id", None)
        if support_tenant_id and str(support_tenant_id) == str(tenant_id).strip():
            return RoleEnum.VIEWER
        return None
    tenant_value = tenant_id.strip()
    tenant = (
        get_tenant_by_id(db, int(tenant_value))
        if tenant_value.isdigit()
        else get_tenant_by_slug(db, tenant_value)
    )
    if not tenant:
        return None
    membership = (
        db.query(Membership)
        .filter(Membership.tenant_id == tenant.id, Membership.user_id == user.id)
        .first()
    )
    if not membership or membership.status != MembershipStatusEnum.ACTIVE:
        return None
    return membership.role


def get_current_membership(
    db: Session,
    current_user,
    tenant_id: Optional[str],
) -> Membership:
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant must be provided via header",
        )
    if getattr(current_user, "support_mode", False):
        support_tenant_id = getattr(current_user, "support_tenant_id", None)
        if not support_tenant_id or str(support_tenant_id) != str(tenant_id).strip():
            status_code = status.HTTP_404_NOT_FOUND if settings.TENANT_STRICT_404 else status.HTTP_403_FORBIDDEN
            raise HTTPException(status_code=status_code, detail="Tenant membership not found")
        return Membership(
            tenant_id=int(support_tenant_id),
            user_id=current_user.id,
            role=RoleEnum.VIEWER,
            status=MembershipStatusEnum.ACTIVE,
        )
    tenant_value = tenant_id.strip()
    tenant = (
        get_tenant_by_id(db, int(tenant_value))
        if tenant_value.isdigit()
        else get_tenant_by_slug(db, tenant_value)
    )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    membership = (
        db.query(Membership)
        .filter(
            Membership.tenant_id == tenant.id,
            Membership.user_id == current_user.id,
        )
        .first()
    )
    if not membership or membership.status != MembershipStatusEnum.ACTIVE:
        status_code = status.HTTP_404_NOT_FOUND if settings.TENANT_STRICT_404 else status.HTTP_403_FORBIDDEN
        raise HTTPException(status_code=status_code, detail="Tenant membership not found")
    return membership


async def get_request_context(
    request: Request,
    db: Session,
    current_user,
) -> RequestContext:
    """
    Extract tenant and user context from the request and authenticated user.
    """
    tenant_id = _resolve_tenant_id(request)
    request_id = getattr(request.state, "request_id", str(uuid4()))
    user_id = getattr(current_user, "id", None)
    username = getattr(current_user, "username", None)
    role = _resolve_membership_role(db, current_user, tenant_id)
    support_mode = bool(getattr(current_user, "support_mode", False))
    support_tenant_id = getattr(current_user, "support_tenant_id", None)
    return RequestContext(
        request_id=request_id,
        tenant_id=tenant_id,
        user_id=user_id,
        username=username,
        role=role,
        support_mode=support_mode,
        support_tenant_id=support_tenant_id,
    )


def require_tenant_context(*, user_resolver: Optional[Callable] = None):
    """
    Dependency that enforces presence of a tenant context and membership.
    """

    if user_resolver is None:
        from app.api.dependencies import get_current_user as user_resolver  # local import to avoid cycles

    async def dependency(
        request: Request,
        db: Session = Depends(get_db),
        current_user=Depends(user_resolver),
    ) -> RequestContext:
        tenant_id = _resolve_tenant_id(request)
        request_id = getattr(request.state, "request_id", str(uuid4()))
        user_id = getattr(current_user, "id", None)
        username = getattr(current_user, "username", None)
        if settings.REQUIRE_TENANT_HEADER and tenant_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tenant must be provided via header",
            )
        support_mode = bool(getattr(current_user, "support_mode", False))
        support_tenant_id = getattr(current_user, "support_tenant_id", None)
        role = None
        if tenant_id is not None:
            if support_mode:
                if not support_tenant_id or str(support_tenant_id) != str(tenant_id).strip():
                    status_code = (
                        status.HTTP_404_NOT_FOUND
                        if settings.TENANT_STRICT_404
                        else status.HTTP_403_FORBIDDEN
                    )
                    raise HTTPException(status_code=status_code, detail="Tenant membership not found")
                role = RoleEnum.VIEWER
            else:
                membership = get_current_membership(db, current_user, tenant_id)
                role = membership.role
        return RequestContext(
            request_id=request_id,
            tenant_id=tenant_id,
            user_id=user_id,
            username=username,
            role=role,
            support_mode=support_mode,
            support_tenant_id=support_tenant_id,
        )

    return dependency


def require_roles(
    roles: Iterable[RoleEnum | str],
    *,
    user_resolver: Optional[Callable] = None,
    allow_higher_roles: bool = True,
):
    """
    Dependency enforcing that the caller has one of the allowed roles.
    """
    def _normalize_role(role: RoleEnum | str) -> RoleEnum:
        if isinstance(role, RoleEnum):
            return role
        return RoleEnum(role)

    base_hierarchy = {
        RoleEnum.VIEWER: 1,
        RoleEnum.ANALYST: 2,
        RoleEnum.ADMIN: 3,
        RoleEnum.OWNER: 4,
    }
    specialized_hierarchy = {
        RoleEnum.SECURITY_ADMIN: 2,
        RoleEnum.BILLING_ADMIN: 1,
    }

    def _role_satisfies(required_roles: set[RoleEnum], actual_role: RoleEnum | None) -> bool:
        if not required_roles:
            return True
        if actual_role is None:
            return False
        if not allow_higher_roles:
            return actual_role in required_roles
        if actual_role in required_roles:
            return True
        if actual_role in base_hierarchy:
            actual_rank = base_hierarchy[actual_role]
            return any(
                required in base_hierarchy and actual_rank >= base_hierarchy[required]
                for required in required_roles
            )
        if actual_role in specialized_hierarchy:
            actual_rank = specialized_hierarchy[actual_role]
            return any(
                required in base_hierarchy and actual_rank >= base_hierarchy[required]
                for required in required_roles
            )
        return False

    role_set = {_normalize_role(role) for role in roles}

    async def dependency(
        ctx: RequestContext = Depends(require_tenant_context(user_resolver=user_resolver)),
    ) -> RequestContext:
        ctx_role = None
        if ctx.role is not None:
            try:
                ctx_role = _normalize_role(ctx.role)
            except ValueError:
                ctx_role = None
        if not _role_satisfies(role_set, ctx_role):
            status_code = status.HTTP_404_NOT_FOUND if settings.TENANT_STRICT_404 else status.HTTP_403_FORBIDDEN
            raise HTTPException(status_code=status_code, detail="Insufficient role for tenant operation")
        return ctx

    return dependency


def require_role_in_tenant(
    roles: Iterable[RoleEnum | str],
    *,
    user_resolver: Optional[Callable] = None,
    allow_higher_roles: bool = True,
):
    """
    Alias for require_roles to emphasize tenant-scoped RBAC usage.
    """
    return require_roles(roles, user_resolver=user_resolver, allow_higher_roles=allow_higher_roles)
