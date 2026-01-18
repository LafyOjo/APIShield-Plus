import os
import time
from datetime import timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "secret")

from app.core.db import Base
from app.core.time import utcnow
from app.crud.tenants import create_tenant


@pytest.fixture
def db_session(tmp_path):
    db_url = f"sqlite:///{tmp_path}/timestamps_test.db"
    os.environ["DATABASE_URL"] = db_url
    os.environ["SKIP_MIGRATIONS"] = "1"
    engine = create_engine(db_url, future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    with TestingSessionLocal() as session:
        yield session


def test_created_at_set_on_insert(db_session):
    tenant = create_tenant(db_session, name="Acme")
    assert tenant.created_at is not None
    assert tenant.updated_at is not None
    if tenant.created_at.tzinfo is not None:
        assert tenant.created_at.tzinfo == timezone.utc


def test_updated_at_changes_on_update(db_session):
    tenant = create_tenant(db_session, name="Acme")
    original = tenant.updated_at
    time.sleep(0.01)
    tenant.name = "Acme Updated"
    db_session.commit()
    db_session.refresh(tenant)
    assert tenant.updated_at > original


def test_utcnow_utility_returns_timezone_consistent_value():
    value = utcnow()
    assert value.tzinfo == timezone.utc
