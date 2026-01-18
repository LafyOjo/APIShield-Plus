import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "secret")

from app.models.api_keys import APIKey
from app.models.enums import RoleEnum
from app.models.memberships import Membership
from app.models.tenants import Tenant
from app.models.websites import Website
from app.seed.utils import (
    get_or_create_api_key,
    get_or_create_membership,
    get_or_create_tenant,
    get_or_create_user,
    get_or_create_website,
    get_environment_by_name,
)
from app.core.db import Base
from app.models.users import User


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    db_url = f"sqlite:///{tmp_path}/seed_test.db"
    os.environ["DATABASE_URL"] = db_url
    os.environ["SKIP_MIGRATIONS"] = "1"
    engine = create_engine(db_url, future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    with TestingSessionLocal() as session:
        yield session


def test_seed_creates_tenant_user_membership(db_session):
    tenant = get_or_create_tenant(db_session, "acme", "Acme Inc")
    user = get_or_create_user(db_session, "alice", "secret")
    membership = get_or_create_membership(db_session, user, tenant, role="owner")

    assert isinstance(tenant, Tenant)
    assert isinstance(user, User)
    assert isinstance(membership, Membership)
    assert membership.role == RoleEnum.OWNER


def test_seed_websites_and_keys(db_session):
    tenant = get_or_create_tenant(db_session, "umbrella", "Umbrella")
    site = get_or_create_website(db_session, tenant, "umbrella-login.com")
    environment = get_environment_by_name(db_session, site)
    assert environment is not None
    key1 = get_or_create_api_key(
        db_session,
        tenant=tenant,
        website=site,
        environment=environment,
        public_key="pk_umbrella_k1",
        raw_secret="sk_umbrella_k1",
        revoked=False,
    )
    key2 = get_or_create_api_key(
        db_session,
        tenant=tenant,
        website=site,
        environment=environment,
        public_key="pk_umbrella_k2",
        raw_secret="sk_umbrella_k2",
        revoked=True,
    )

    assert isinstance(site, Website)
    assert isinstance(key1, APIKey)
    assert key2.revoked_at is not None
