import os
import asyncio
import types

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure required settings exist before imports.
os.environ.setdefault("SKIP_MIGRATIONS", "1")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "secret")

from app.tenancy.context import RequestContext
from app.core.config import settings
from app.models.enums import MembershipStatusEnum, RoleEnum
from app.tenancy.dependencies import (
    get_request_context,
    get_current_membership,
    require_roles,
    require_tenant_context,
)
from app.tenancy.scoping import scoped_query
from app.core.db import Base
from app.core.security import get_password_hash
from app.crud.tenants import create_tenant
from app.crud.users import create_user
from app.crud.memberships import create_membership


def _request(headers=None):
    scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
    if headers:
        scope["headers"] = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request(scope)


@pytest.fixture
def db_session(tmp_path):
    db_url = f"sqlite:///{tmp_path}/tenancy_context.db"
    os.environ["DATABASE_URL"] = db_url
    os.environ["SKIP_MIGRATIONS"] = "1"
    engine = create_engine(db_url, future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    with TestingSessionLocal() as session:
        yield session


def test_get_request_context_resolves_tenant_and_role(db_session):
    tenant = create_tenant(db_session, name="Acme")
    owner_row = create_user(db_session, username="owner", password_hash=get_password_hash("pw"), role="user")
    create_membership(
        db_session,
        tenant_id=tenant.id,
        user_id=owner_row.id,
        role="owner",
        created_by_user_id=owner_row.id,
    )
    user_row = create_user(db_session, username="alice", password_hash=get_password_hash("pw"), role="user")
    create_membership(
        db_session,
        tenant_id=tenant.id,
        user_id=user_row.id,
        role="admin",
        created_by_user_id=user_row.id,
    )
    user = types.SimpleNamespace(id=user_row.id, username="alice", role="user")
    ctx = asyncio.run(
        get_request_context(
            request=_request({"X-Tenant-ID": tenant.slug}),
            db=db_session,
            current_user=user,
        )
    )
    assert isinstance(ctx, RequestContext)
    assert ctx.tenant_id == tenant.slug
    assert ctx.role == RoleEnum.ADMIN
    assert ctx.username == "alice"


def test_require_tenant_context_missing_header_errors(db_session):
    dep = require_tenant_context(user_resolver=lambda: None)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(dep(request=_request(), db=db_session, current_user=None))
    assert exc.value.status_code == 400


def test_require_tenant_context_non_member_errors(db_session):
    dep = require_tenant_context(user_resolver=lambda: None)
    tenant = create_tenant(db_session, name="Umbrella")
    user_row = create_user(db_session, username="bob", password_hash=get_password_hash("pw"), role="user")
    user = types.SimpleNamespace(id=user_row.id, username="bob", role="user")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            dep(
                request=_request({"X-Tenant-ID": tenant.slug}),
                db=db_session,
                current_user=user,
            )
        )
    expected = 404 if settings.TENANT_STRICT_404 else 403
    assert exc.value.status_code == expected


def test_require_roles_accepts_matching_role():
    dep = require_roles(["admin"], user_resolver=lambda: None)
    ctx = RequestContext(request_id="r1", tenant_id="t1", user_id=1, username="alice", role=RoleEnum.ADMIN)
    result = asyncio.run(dep(ctx=ctx))
    assert result is ctx


def test_require_roles_rejects_mismatched_role():
    dep = require_roles(["admin"], user_resolver=lambda: None)
    ctx = RequestContext(request_id="r1", tenant_id="t1", user_id=1, username="bob", role=RoleEnum.VIEWER)
    with pytest.raises(HTTPException):
        asyncio.run(dep(ctx=ctx))


def test_require_roles_allows_owner_admin():
    dep = require_roles([RoleEnum.ADMIN], user_resolver=lambda: None, allow_higher_roles=True)
    ctx = RequestContext(request_id="r1", tenant_id="t1", user_id=1, username="alice", role=RoleEnum.OWNER)
    result = asyncio.run(dep(ctx=ctx))
    assert result is ctx


def test_require_roles_blocks_viewer():
    dep = require_roles([RoleEnum.ADMIN], user_resolver=lambda: None, allow_higher_roles=True)
    ctx = RequestContext(request_id="r1", tenant_id="t1", user_id=1, username="bob", role=RoleEnum.VIEWER)
    with pytest.raises(HTTPException):
        asyncio.run(dep(ctx=ctx))


def test_require_roles_enforces_role_hierarchy_if_enabled():
    dep = require_roles([RoleEnum.ANALYST], user_resolver=lambda: None, allow_higher_roles=True)
    ctx = RequestContext(request_id="r1", tenant_id="t1", user_id=1, username="carol", role=RoleEnum.ADMIN)
    result = asyncio.run(dep(ctx=ctx))
    assert result is ctx


def test_scoped_query_no_tenant_attr():
    class Dummy:
        pass

    class FakeSession:
        def query(self, model):
            return self

        def filter(self, *_args, **_kwargs):
            return self

    with pytest.raises(ValueError):
        scoped_query(FakeSession(), Dummy, tenant_id="t1")


def test_get_current_membership_returns_membership_for_valid_user_and_tenant(db_session):
    tenant = create_tenant(db_session, name="Acme")
    owner_row = create_user(db_session, username="owner2", password_hash=get_password_hash("pw"), role="user")
    create_membership(
        db_session,
        tenant_id=tenant.id,
        user_id=owner_row.id,
        role="owner",
        created_by_user_id=owner_row.id,
    )
    user_row = create_user(db_session, username="member", password_hash=get_password_hash("pw"), role="user")
    membership = create_membership(
        db_session,
        tenant_id=tenant.id,
        user_id=user_row.id,
        role="admin",
        created_by_user_id=user_row.id,
    )
    result = get_current_membership(db_session, user_row, tenant.slug)
    assert result.id == membership.id


def test_get_current_membership_rejects_suspended_membership(db_session):
    tenant = create_tenant(db_session, name="Umbrella")
    owner = create_user(db_session, username="owner", password_hash=get_password_hash("pw"), role="user")
    create_membership(
        db_session,
        tenant_id=tenant.id,
        user_id=owner.id,
        role="owner",
        created_by_user_id=owner.id,
    )
    user_row = create_user(db_session, username="suspended", password_hash=get_password_hash("pw"), role="user")
    create_membership(
        db_session,
        tenant_id=tenant.id,
        user_id=user_row.id,
        role="viewer",
        created_by_user_id=owner.id,
        status=MembershipStatusEnum.SUSPENDED,
    )
    with pytest.raises(HTTPException) as exc:
        get_current_membership(db_session, user_row, tenant.slug)
    expected = 404 if settings.TENANT_STRICT_404 else 403
    assert exc.value.status_code == expected


def test_get_current_membership_cross_tenant_returns_404(db_session):
    tenant_a = create_tenant(db_session, name="Tenant A")
    tenant_b = create_tenant(db_session, name="Tenant B")
    owner_row = create_user(db_session, username="owner3", password_hash=get_password_hash("pw"), role="user")
    create_membership(
        db_session,
        tenant_id=tenant_a.id,
        user_id=owner_row.id,
        role="owner",
        created_by_user_id=owner_row.id,
    )
    user_row = create_user(db_session, username="alice", password_hash=get_password_hash("pw"), role="user")
    create_membership(
        db_session,
        tenant_id=tenant_a.id,
        user_id=user_row.id,
        role="admin",
        created_by_user_id=user_row.id,
    )
    with pytest.raises(HTTPException) as exc:
        get_current_membership(db_session, user_row, tenant_b.slug)
    expected = 404 if settings.TENANT_STRICT_404 else 403
    assert exc.value.status_code == expected
