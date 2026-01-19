import os
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ["SKIP_MIGRATIONS"] = "1"

from app.core.db import Base
import app.core.db as db_module
import app.core.access_log as access_log_module
import app.core.policy as policy_module
from app.core.security import get_password_hash
from app.crud.behaviour_events import create_behaviour_event
from app.crud.memberships import create_membership
from app.crud.tenants import create_tenant
from app.crud.users import create_user
from app.crud.website_environments import list_environments
from app.crud.websites import create_website
from app.models.behaviour_events import BehaviourEvent
from app.models.enums import RoleEnum


def _setup_db(db_url: str):
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        future=True,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db_module.engine = engine
    db_module.SessionLocal = SessionLocal
    access_log_module.SessionLocal = SessionLocal
    policy_module.SessionLocal = SessionLocal
    access_log_module.create_access_log = lambda db, username, path: None
    Base.metadata.create_all(bind=engine)
    return SessionLocal, engine


def _seed_tenant(SessionLocal, *, username: str, tenant_name: str, domain: str):
    with SessionLocal() as db:
        user = create_user(db, username=username, password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name=tenant_name)
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=user.id,
            role=RoleEnum.OWNER,
            created_by_user_id=user.id,
        )
        website = create_website(db, tenant.id, domain, created_by_user_id=user.id)
        environment = list_environments(db, website.id)[0]
        return tenant.id, website.id, environment.id


def test_behaviour_event_insert_and_query_scoped():
    db_url = f"sqlite:///./behaviour_events_{uuid4().hex}.db"
    SessionLocal, _engine = _setup_db(db_url)

    tenant_a_id, website_a_id, env_a_id = _seed_tenant(
        SessionLocal,
        username="alice",
        tenant_name="TenantA",
        domain="a.example.com",
    )
    tenant_b_id, website_b_id, env_b_id = _seed_tenant(
        SessionLocal,
        username="bob",
        tenant_name="TenantB",
        domain="b.example.com",
    )

    with SessionLocal() as db:
        create_behaviour_event(
            db,
            tenant_id=tenant_a_id,
            website_id=website_a_id,
            environment_id=env_a_id,
            event_id=str(uuid4()),
            event_type="page_view",
            url="https://a.example.com/",
            event_ts=datetime.now(timezone.utc),
            path="/",
            session_id="sess-a",
        )
        create_behaviour_event(
            db,
            tenant_id=tenant_b_id,
            website_id=website_b_id,
            environment_id=env_b_id,
            event_id=str(uuid4()),
            event_type="page_view",
            url="https://b.example.com/",
            event_ts=datetime.now(timezone.utc),
            path="/",
            session_id="sess-b",
        )
        events_a = (
            db.query(BehaviourEvent)
            .filter(BehaviourEvent.tenant_id == tenant_a_id)
            .all()
        )
        events_b = (
            db.query(BehaviourEvent)
            .filter(BehaviourEvent.tenant_id == tenant_b_id)
            .all()
        )
        assert len(events_a) == 1
        assert len(events_b) == 1
        assert events_a[0].tenant_id != events_b[0].tenant_id


def test_behaviour_event_indexes_exist_or_migration_contains_indexes():
    db_url = f"sqlite:///./behaviour_events_indexes_{uuid4().hex}.db"
    _SessionLocal, engine = _setup_db(db_url)
    inspector = inspect(engine)
    indexes = {idx["name"] for idx in inspector.get_indexes("behaviour_events")}
    expected = {
        "ix_behaviour_events_tenant_ingested_at",
        "ix_behaviour_events_tenant_website_ingested_at",
        "ix_behaviour_events_tenant_session_ingested_at",
        "ix_behaviour_events_tenant_session_event_ts",
        "ix_behaviour_events_tenant_path_ingested_at",
        "ix_behaviour_events_tenant_ip_hash_ingested_at",
    }
    assert expected.issubset(indexes)
