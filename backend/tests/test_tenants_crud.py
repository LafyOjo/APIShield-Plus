import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "secret")

from app.core.db import Base
from app.crud.tenants import (
    create_tenant,
    get_tenant_by_id,
    get_tenant_by_slug,
    list_tenants,
    restore_tenant,
    soft_delete_tenant,
)
from app.models.tenants import Tenant


@pytest.fixture
def db_session(tmp_path):
    db_url = f"sqlite:///{tmp_path}/tenants_test.db"
    os.environ["DATABASE_URL"] = db_url
    os.environ["SKIP_MIGRATIONS"] = "1"
    engine = create_engine(db_url, future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    with TestingSessionLocal() as session:
        yield session


def test_create_tenant_generates_slug(db_session):
    tenant = create_tenant(db_session, name="Acme Inc")
    assert tenant.slug == "acme-inc"


def test_create_tenant_slug_collision_appends_suffix(db_session):
    first = create_tenant(db_session, name="Acme")
    second = create_tenant(db_session, name="Acme")
    assert first.slug == "acme"
    assert second.slug == "acme-2"


def test_get_tenant_by_slug_returns_correct_tenant(db_session):
    tenant = create_tenant(db_session, name="Umbrella Corp")
    found = get_tenant_by_slug(db_session, tenant.slug)
    assert found is not None
    assert found.id == tenant.id


def test_soft_delete_tenant_sets_deleted_at(db_session):
    tenant = create_tenant(db_session, name="Delete Me")
    deleted = soft_delete_tenant(db_session, tenant.id)
    assert deleted is not None
    assert deleted.deleted_at is not None


def test_soft_delete_tenant_hides_it_from_lists(db_session):
    tenant = create_tenant(db_session, name="Hidden Tenant")
    soft_delete_tenant(db_session, tenant.id)
    assert list_tenants(db_session) == []
    assert list_tenants(db_session, include_deleted=True)[0].id == tenant.id


def test_access_deleted_tenant_returns_none(db_session):
    tenant = create_tenant(db_session, name="Gone Tenant")
    soft_delete_tenant(db_session, tenant.id)
    assert get_tenant_by_id(db_session, tenant.id) is None
    assert get_tenant_by_slug(db_session, tenant.slug) is None


def test_restore_deleted_tenant(db_session):
    tenant = create_tenant(db_session, name="Restore Tenant")
    soft_delete_tenant(db_session, tenant.id)
    restored = restore_tenant(db_session, tenant.id)
    assert restored is not None
    assert restored.deleted_at is None
    assert get_tenant_by_id(db_session, tenant.id) is not None


def test_tenant_slug_duplicate_fails(db_session):
    first = Tenant(name="Acme", slug="acme")
    db_session.add(first)
    db_session.commit()
    db_session.refresh(first)

    duplicate = Tenant(name="Acme 2", slug="acme")
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
