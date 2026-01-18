import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "secret")

from app.core.db import Base
from app.crud.events import create_event, get_events
from app.crud.tenants import create_tenant


@pytest.fixture
def db_session(tmp_path):
    db_url = f"sqlite:///{tmp_path}/events_tenant_test.db"
    os.environ["DATABASE_URL"] = db_url
    os.environ["SKIP_MIGRATIONS"] = "1"
    engine = create_engine(db_url, future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    with TestingSessionLocal() as session:
        yield session


def test_event_creation_requires_tenant_id(db_session):
    with pytest.raises(ValueError):
        create_event(db_session, None, "alice", "login", True)


def test_list_events_is_tenant_scoped(db_session):
    tenant_a = create_tenant(db_session, name="Tenant A")
    tenant_b = create_tenant(db_session, name="Tenant B")
    create_event(db_session, tenant_a.id, "alice", "login", True)
    create_event(db_session, tenant_b.id, "bob", "login", True)

    events_a = get_events(db_session, tenant_a.id)
    assert len(events_a) == 1
    assert all(event.tenant_id == tenant_a.id for event in events_a)


def test_cross_tenant_event_access_blocked(db_session):
    tenant_a = create_tenant(db_session, name="Tenant A")
    tenant_b = create_tenant(db_session, name="Tenant B")
    create_event(db_session, tenant_a.id, "alice", "login", True)
    create_event(db_session, tenant_b.id, "bob", "login", True)

    events_b = get_events(db_session, tenant_b.id)
    assert len(events_b) == 1
    assert all(event.tenant_id == tenant_b.id for event in events_b)
