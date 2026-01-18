from uuid import uuid4

from app.core.security import get_password_hash
from app.crud.api_keys import create_api_key
from app.crud.memberships import create_membership
from app.crud.tenants import create_tenant
from app.crud.users import create_user
from app.crud.website_environments import list_environments
from app.crud.websites import create_website
from app.models.enums import RoleEnum


def make_user(db, *, username: str | None = None, role: str = "user"):
    username = username or f"user_{uuid4().hex[:8]}"
    return create_user(db, username=username, password_hash=get_password_hash("pw"), role=role)


def make_tenant(db, *, name: str | None = None, slug: str | None = None, created_by_user_id: int | None = None):
    name = name or f"Tenant {uuid4().hex[:6]}"
    return create_tenant(db, name=name, slug=slug, created_by_user_id=created_by_user_id)


def make_membership(db, *, tenant, user, role: RoleEnum = RoleEnum.OWNER, created_by_user_id: int | None = None):
    return create_membership(
        db,
        tenant_id=tenant.id,
        user_id=user.id,
        role=role,
        created_by_user_id=created_by_user_id or user.id,
    )


def make_website(db, *, tenant, domain: str | None = None, created_by_user_id: int | None = None):
    domain = domain or f"site-{uuid4().hex[:6]}.example.com"
    return create_website(db, tenant.id, domain, created_by_user_id=created_by_user_id)


def get_default_environment(db, *, website):
    return list_environments(db, website.id)[0]


def make_api_key(
    db,
    *,
    tenant,
    website,
    environment=None,
    name: str | None = None,
    created_by_user_id: int | None = None,
):
    environment = environment or get_default_environment(db, website=website)
    return create_api_key(
        db,
        tenant_id=tenant.id,
        website_id=website.id,
        environment_id=environment.id,
        name=name,
        created_by_user_id=created_by_user_id,
    )
