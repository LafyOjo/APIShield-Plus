import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "secret")

from app.core.db import Base
from app.core.security import get_password_hash
from app.crud.api_keys import create_api_key
from app.crud.memberships import create_membership
from app.crud.tenants import create_tenant
from app.crud.users import create_user
from app.crud.website_environments import list_environments
from app.crud.websites import create_website
from app.models.enums import RoleEnum


@pytest.fixture
def db_session(tmp_path):
    db_url = f"sqlite:///{tmp_path}/relationships_test.db"
    os.environ["DATABASE_URL"] = db_url
    os.environ["SKIP_MIGRATIONS"] = "1"
    engine = create_engine(db_url, future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    with TestingSessionLocal() as session:
        yield session


def test_tenant_has_websites_relationship(db_session):
    tenant = create_tenant(db_session, name="Acme")
    website = create_website(db_session, tenant.id, "acme.com")
    db_session.expire(tenant)
    assert [site.id for site in tenant.websites] == [website.id]


def test_website_has_environments_relationship(db_session):
    tenant = create_tenant(db_session, name="Umbrella")
    website = create_website(db_session, tenant.id, "umbrella.com")
    db_session.expire(website)
    assert len(website.environments) == 1
    assert website.environments[0].name == "production"


def test_user_has_memberships_relationship(db_session):
    tenant = create_tenant(db_session, name="Wayne")
    user = create_user(db_session, username="bruce", password_hash=get_password_hash("pw"), role="user")
    membership = create_membership(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        role=RoleEnum.OWNER,
        created_by_user_id=user.id,
    )
    db_session.expire(user)
    assert [m.id for m in user.memberships] == [membership.id]


def test_api_key_links_environment_and_tenant(db_session):
    tenant = create_tenant(db_session, name="Stark")
    user = create_user(db_session, username="tony", password_hash=get_password_hash("pw"), role="user")
    website = create_website(db_session, tenant.id, "stark.com", created_by_user_id=user.id)
    environment = list_environments(db_session, website.id)[0]
    api_key, _raw_secret = create_api_key(
        db_session,
        tenant_id=tenant.id,
        website_id=website.id,
        environment_id=environment.id,
        name="Primary",
        created_by_user_id=user.id,
    )
    db_session.expire(api_key)
    assert api_key.tenant.id == tenant.id
    assert api_key.website.id == website.id
    assert api_key.environment.id == environment.id
    db_session.expire(environment)
    assert [key.id for key in environment.api_keys] == [api_key.id]
    db_session.expire(tenant)
    assert [key.id for key in tenant.api_keys] == [api_key.id]
