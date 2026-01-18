"""
Helpers to ensure database access stays tenant-scoped.
"""

from functools import wraps
import inspect
from sqlalchemy.orm import Session

from app.tenancy.context import RequestContext
from app.tenancy.errors import TenantNotFound, TenantNotSelected


def _ensure_model_has_tenant_id(model) -> None:
    if not hasattr(model, "tenant_id"):
        name = getattr(model, "__name__", str(model))
        raise ValueError(f"{name} does not define tenant_id and cannot be tenant-scoped.")


def scoped_query(db: Session, model, tenant_id):
    """
    Return a query constrained to the given tenant.

    Example:
        scoped_query(db, Website, tenant_id).all()
    """
    _ensure_model_has_tenant_id(model)
    return db.query(model).filter(model.tenant_id == tenant_id)


def get_tenant_owned_or_404(db: Session, model, tenant_id, object_id):
    """
    Fetch by id + tenant_id or raise TenantNotFound (404 style).
    """
    _ensure_model_has_tenant_id(model)
    resource = scoped_query(db, model, tenant_id).filter(model.id == object_id).first()
    if not resource:
        raise TenantNotFound("Resource not found for tenant")
    return resource


def assert_belongs_to_tenant(resource, tenant_id, *, not_found_ok: bool = False):
    """
    Guard that a loaded resource matches the requested tenant.
    """
    if resource is None:
        if not_found_ok:
            return None
        raise TenantNotFound("Resource not found for tenant")

    resource_tenant = getattr(resource, "tenant_id", None)
    if resource_tenant != tenant_id:
        raise TenantNotFound("Resource not found for tenant")
    return resource


def tenant_scoped(handler):
    """
    Decorator stub that ensures a RequestContext with tenant_id is present.

    Example:
        @tenant_scoped
        def handler(ctx: RequestContext, ...):
            ...
    """
    async def _ensure_ctx(kwargs):
        ctx = kwargs.get("ctx")
        if ctx is None or not isinstance(ctx, RequestContext) or ctx.tenant_id is None:
            raise TenantNotSelected("Tenant context required")

    if inspect.iscoroutinefunction(handler):
        @wraps(handler)
        async def async_wrapper(*args, **kwargs):
            await _ensure_ctx(kwargs)
            return await handler(*args, **kwargs)

        return async_wrapper

    @wraps(handler)
    def sync_wrapper(*args, **kwargs):
        ctx = kwargs.get("ctx")
        if ctx is None or not isinstance(ctx, RequestContext) or ctx.tenant_id is None:
            raise TenantNotSelected("Tenant context required")
        return handler(*args, **kwargs)

    return sync_wrapper
