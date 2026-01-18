import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "secret")

from app.core.db import Base
from app.crud.tenants import create_tenant
from app.crud.users import create_user
from app.crud.websites import (
    create_website,
    get_website,
    list_websites,
    pause_website,
    resume_website,
    restore_website,
    soft_delete_website,
)
from app.core.security import get_password_hash
from app.models.enums import WebsiteStatusEnum
from app.models.websites import Website
from app.tenancy.errors import TenantNotFound


@pytest.fixture
def db_session(tmp_path):
    db_url = f"sqlite:///{tmp_path}/websites_test.db"
    os.environ["DATABASE_URL"] = db_url
    os.environ["SKIP_MIGRATIONS"] = "1"
    engine = create_engine(db_url, future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    with TestingSessionLocal() as session:
        yield session


def test_create_website_normalizes_domain(db_session):
    tenant = create_tenant(db_session, name="Acme")
    website = create_website(db_session, tenant.id, "https://Example.com/")
    assert website.domain == "example.com"


def test_create_website_sets_created_by_user_id(db_session):
    tenant = create_tenant(db_session, name="Acme")
    user = create_user(db_session, username="creator", password_hash=get_password_hash("pw"))
    website = create_website(
        db_session,
        tenant.id,
        "creator.com",
        created_by_user_id=user.id,
    )
    assert website.created_by_user_id == user.id


def test_create_website_duplicate_domain_same_tenant_fails(db_session):
    tenant = create_tenant(db_session, name="Acme")
    create_website(db_session, tenant.id, "example.com")
    with pytest.raises(ValueError):
        create_website(db_session, tenant.id, "example.com")


def test_create_website_same_domain_different_tenant_allowed(db_session):
    tenant_a = create_tenant(db_session, name="Acme")
    tenant_b = create_tenant(db_session, name="Umbrella")
    website_a = create_website(db_session, tenant_a.id, "example.com")
    website_b = create_website(db_session, tenant_b.id, "example.com")
    assert website_a.id != website_b.id


def test_soft_delete_website_sets_deleted_at_and_status(db_session):
    tenant = create_tenant(db_session, name="Acme")
    website = create_website(db_session, tenant.id, "example.com")
    deleted = soft_delete_website(db_session, tenant.id, website.id)
    assert deleted is not None
    assert deleted.status == WebsiteStatusEnum.DELETED
    assert deleted.deleted_at is not None


def test_deleted_websites_hidden_from_default_list(db_session):
    tenant = create_tenant(db_session, name="Acme")
    website = create_website(db_session, tenant.id, "example.com")
    soft_delete_website(db_session, tenant.id, website.id)
    assert list_websites(db_session, tenant.id) == []
    assert list_websites(db_session, tenant.id, include_deleted=True)[0].id == website.id


def test_access_deleted_website_returns_none(db_session):
    tenant = create_tenant(db_session, name="Acme")
    website = create_website(db_session, tenant.id, "example.com")
    soft_delete_website(db_session, tenant.id, website.id)
    with pytest.raises(TenantNotFound):
        get_website(db_session, tenant.id, website.id)


def test_restore_deleted_website(db_session):
    tenant = create_tenant(db_session, name="Acme")
    website = create_website(db_session, tenant.id, "example.com")
    soft_delete_website(db_session, tenant.id, website.id)
    restored = restore_website(db_session, tenant.id, website.id)
    assert restored is not None
    assert restored.deleted_at is None
    assert restored.status == WebsiteStatusEnum.ACTIVE


def test_pause_and_resume_website_status_changes(db_session):
    tenant = create_tenant(db_session, name="Acme")
    website = create_website(db_session, tenant.id, "paused.com")
    paused = pause_website(db_session, tenant.id, website.id)
    assert paused is not None
    assert paused.status == WebsiteStatusEnum.PAUSED
    resumed = resume_website(db_session, tenant.id, website.id)
    assert resumed is not None
    assert resumed.status == WebsiteStatusEnum.ACTIVE


def test_domain_unique_constraint_enforced(db_session):
    tenant = create_tenant(db_session, name="Acme")
    website = Website(tenant_id=tenant.id, domain="example.com", status=WebsiteStatusEnum.ACTIVE)
    db_session.add(website)
    db_session.commit()
    db_session.refresh(website)

    duplicate = Website(tenant_id=tenant.id, domain="example.com", status=WebsiteStatusEnum.ACTIVE)
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_legacy_rows_allow_null_created_by_user_id(db_session):
    tenant = create_tenant(db_session, name="Legacy")
    website = create_website(db_session, tenant.id, "legacy.com")
    assert website.created_by_user_id is None
