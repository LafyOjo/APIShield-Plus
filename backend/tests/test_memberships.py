import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "secret")

from app.core.db import Base
from app.core.security import get_password_hash
from app.crud.memberships import create_membership, remove_membership, update_membership_role
from app.crud.tenants import create_tenant
from app.crud.users import create_user
from app.models.enums import MembershipStatusEnum, RoleEnum
from app.models.memberships import Membership


@pytest.fixture
def db_session(tmp_path):
    db_url = f"sqlite:///{tmp_path}/memberships_test.db"
    os.environ["DATABASE_URL"] = db_url
    os.environ["SKIP_MIGRATIONS"] = "1"
    engine = create_engine(db_url, future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    with TestingSessionLocal() as session:
        yield session


def test_membership_create_uniqueness(db_session):
    tenant = create_tenant(db_session, name="Acme")
    user = create_user(db_session, username="alice", password_hash=get_password_hash("pw"), role="user")
    create_membership(db_session, tenant_id=tenant.id, user_id=user.id, role="owner", created_by_user_id=user.id)
    create_membership(db_session, tenant_id=tenant.id, user_id=user.id, role="owner", created_by_user_id=user.id)

    count = db_session.query(Membership).count()
    assert count == 1


def test_owner_cannot_remove_last_owner(db_session):
    tenant = create_tenant(db_session, name="Umbrella")
    user = create_user(db_session, username="bob", password_hash=get_password_hash("pw"), role="user")
    membership = create_membership(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        role="owner",
        created_by_user_id=user.id,
    )
    with pytest.raises(ValueError):
        remove_membership(db_session, tenant_id=tenant.id, membership_id=membership.id)


def test_cannot_demote_last_owner(db_session):
    tenant = create_tenant(db_session, name="Wayne")
    user = create_user(db_session, username="bruce", password_hash=get_password_hash("pw"), role="user")
    membership = create_membership(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        role=RoleEnum.OWNER,
        created_by_user_id=user.id,
    )
    with pytest.raises(ValueError):
        update_membership_role(
            db_session,
            tenant_id=tenant.id,
            membership_id=membership.id,
            role=RoleEnum.ADMIN,
        )


def test_can_remove_owner_if_multiple_owners_exist(db_session):
    tenant = create_tenant(db_session, name="Stark")
    owner1 = create_user(db_session, username="tony", password_hash=get_password_hash("pw"), role="user")
    owner2 = create_user(db_session, username="pepper", password_hash=get_password_hash("pw"), role="user")
    membership1 = create_membership(
        db_session,
        tenant_id=tenant.id,
        user_id=owner1.id,
        role=RoleEnum.OWNER,
        created_by_user_id=owner1.id,
    )
    create_membership(
        db_session,
        tenant_id=tenant.id,
        user_id=owner2.id,
        role=RoleEnum.OWNER,
        created_by_user_id=owner1.id,
    )
    removed = remove_membership(db_session, tenant_id=tenant.id, membership_id=membership1.id)
    assert removed is not None
    assert removed.status == MembershipStatusEnum.SUSPENDED


def test_user_can_belong_to_multiple_tenants(db_session):
    user = create_user(db_session, username="multi", password_hash=get_password_hash("pw"), role="user")
    tenant_a = create_tenant(db_session, name="Tenant A")
    tenant_b = create_tenant(db_session, name="Tenant B")
    create_membership(
        db_session,
        tenant_id=tenant_a.id,
        user_id=user.id,
        role="owner",
        created_by_user_id=user.id,
    )
    create_membership(
        db_session,
        tenant_id=tenant_b.id,
        user_id=user.id,
        role="viewer",
        created_by_user_id=user.id,
    )
    count = db_session.query(Membership).filter(Membership.user_id == user.id).count()
    assert count == 2


def test_invalid_role_rejected(db_session):
    tenant = create_tenant(db_session, name="Acme")
    user = create_user(db_session, username="invalid", password_hash=get_password_hash("pw"), role="user")
    with pytest.raises(ValueError):
        create_membership(
            db_session,
            tenant_id=tenant.id,
            user_id=user.id,
            role="not-a-role",
            created_by_user_id=user.id,
        )


def test_membership_role_roundtrip_enum(db_session):
    tenant = create_tenant(db_session, name="Acme")
    user = create_user(db_session, username="enum", password_hash=get_password_hash("pw"), role="user")
    membership = create_membership(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        role=RoleEnum.OWNER,
        created_by_user_id=user.id,
    )
    assert membership.role == RoleEnum.OWNER
    assert membership.status == MembershipStatusEnum.ACTIVE
