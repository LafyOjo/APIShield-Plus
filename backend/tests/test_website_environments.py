import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "secret")

from app.core.db import Base
from app.crud.tenants import create_tenant
from app.crud.website_environments import create_environment, list_environments
from app.crud.websites import create_website


@pytest.fixture
def db_session(tmp_path):
    db_url = f"sqlite:///{tmp_path}/website_envs_test.db"
    os.environ["DATABASE_URL"] = db_url
    os.environ["SKIP_MIGRATIONS"] = "1"
    engine = create_engine(db_url, future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    with TestingSessionLocal() as session:
        yield session


def test_new_website_creates_default_production_environment(db_session):
    tenant = create_tenant(db_session, name="Acme")
    website = create_website(db_session, tenant.id, "acme.com")

    envs = list_environments(db_session, website.id)

    assert len(envs) == 1
    assert envs[0].name == "production"


def test_create_environment_duplicate_name_same_website_fails(db_session):
    tenant = create_tenant(db_session, name="Umbrella")
    website = create_website(db_session, tenant.id, "umbrella.com")

    create_environment(db_session, website.id, "staging")
    with pytest.raises(ValueError):
        create_environment(db_session, website.id, "staging")


def test_list_environments_returns_only_for_website(db_session):
    tenant = create_tenant(db_session, name="Wayne")
    website_a = create_website(db_session, tenant.id, "wayne.com")
    website_b = create_website(db_session, tenant.id, "wayne-enterprises.com")

    create_environment(db_session, website_a.id, "staging")
    envs_a = list_environments(db_session, website_a.id)
    envs_b = list_environments(db_session, website_b.id)

    assert {env.name for env in envs_a} == {"production", "staging"}
    assert {env.name for env in envs_b} == {"production"}
