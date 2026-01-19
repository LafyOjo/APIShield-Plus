import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("ZERO_TRUST_API_KEY", "")
os.environ["SKIP_MIGRATIONS"] = "1"

from app.main import app
import app.core.db as db_module
import app.core.access_log as access_log_module
import app.core.policy as policy_module
from app.core.rate_limit import reset_state
from app.core.security import get_password_hash
from app.crud.api_keys import create_api_key
from app.crud.memberships import create_membership
from app.crud.tenants import create_tenant
from app.crud.users import create_user
from app.crud.website_environments import create_environment, list_environments
from app.crud.websites import create_website
from app.crud.behaviour_sessions import upsert_behaviour_session
from app.models.behaviour_sessions import BehaviourSession
from app.models.enums import RoleEnum


client = TestClient(app)


def _setup_db(db_url: str):
    reset_state()
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
    db_module.Base.metadata.create_all(bind=engine)
    return SessionLocal


def _setup_ingest(SessionLocal, *, username: str, tenant_name: str, domain: str):
    with SessionLocal() as db:
        owner = create_user(db, username=username, password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name=tenant_name)
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=owner.id,
            role=RoleEnum.OWNER,
            created_by_user_id=owner.id,
        )
        website = create_website(db, tenant.id, domain, created_by_user_id=owner.id)
        environment = list_environments(db, website.id)[0]
        api_key, _raw_secret = create_api_key(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            environment_id=environment.id,
            name="Session Key",
            created_by_user_id=owner.id,
        )
        db.commit()
        return tenant.id, website.id, environment.id, api_key.public_key


def test_ingest_creates_session_if_missing():
    db_url = f"sqlite:///./ingest_session_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_id, website_id, environment_id, api_key = _setup_ingest(
        SessionLocal,
        username="session-user",
        tenant_name="SessionTenant",
        domain="example.com",
    )

    session_id = f"s_{uuid4().hex}"
    payload = {
        "event_id": str(uuid4()),
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": "page_view",
        "url": "https://example.com/home",
        "path": "/home",
        "session_id": session_id,
    }
    resp = client.post(
        "/api/v1/ingest/browser",
        json=payload,
        headers={"X-Api-Key": api_key},
    )
    assert resp.status_code == 200

    with SessionLocal() as db:
        session = (
            db.query(BehaviourSession)
            .filter(
                BehaviourSession.tenant_id == tenant_id,
                BehaviourSession.environment_id == environment_id,
            )
            .first()
        )
        assert session is not None
        assert session.website_id == website_id
        assert session.session_id == session_id
        assert session.page_views == 1
        assert session.event_count == 1
        assert session.entry_path == "/home"
        assert session.exit_path == "/home"


def test_ingest_updates_last_seen_and_counts():
    db_url = f"sqlite:///./ingest_session_update_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_id, _website_id, environment_id, api_key = _setup_ingest(
        SessionLocal,
        username="session-update",
        tenant_name="SessionUpdateTenant",
        domain="example.com",
    )

    session_id = f"s_{uuid4().hex}"
    first_ts = datetime.now(timezone.utc)
    second_ts = first_ts + timedelta(minutes=5)

    payload_one = {
        "event_id": str(uuid4()),
        "ts": first_ts.isoformat(),
        "type": "page_view",
        "url": "https://example.com/start",
        "path": "/start",
        "session_id": session_id,
    }
    payload_two = {
        "event_id": str(uuid4()),
        "ts": second_ts.isoformat(),
        "type": "click",
        "url": "https://example.com/next",
        "path": "/next",
        "session_id": session_id,
    }
    resp = client.post(
        "/api/v1/ingest/browser",
        json=payload_one,
        headers={"X-Api-Key": api_key},
    )
    assert resp.status_code == 200
    resp = client.post(
        "/api/v1/ingest/browser",
        json=payload_two,
        headers={"X-Api-Key": api_key},
    )
    assert resp.status_code == 200

    with SessionLocal() as db:
        session = (
            db.query(BehaviourSession)
            .filter(
                BehaviourSession.tenant_id == tenant_id,
                BehaviourSession.environment_id == environment_id,
            )
            .first()
        )
        assert session is not None
        assert session.event_count == 2
        assert session.page_views == 1
        assert session.last_seen_at == second_ts.replace(tzinfo=None)
        assert session.exit_path == "/next"


def test_session_unique_per_environment():
    db_url = f"sqlite:///./behaviour_session_unique_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_id, website_id, environment_id, _api_key = _setup_ingest(
        SessionLocal,
        username="session-unique",
        tenant_name="SessionUniqueTenant",
        domain="example.com",
    )

    with SessionLocal() as db:
        environment_two = create_environment(db, website_id, "staging")
        session_id = f"s_{uuid4().hex}"
        event_ts = datetime.now(timezone.utc)

        upsert_behaviour_session(
            db,
            tenant_id=tenant_id,
            website_id=website_id,
            environment_id=environment_id,
            session_id=session_id,
            event_type="page_view",
            event_ts=event_ts,
            path="/",
        )
        upsert_behaviour_session(
            db,
            tenant_id=tenant_id,
            website_id=website_id,
            environment_id=environment_two.id,
            session_id=session_id,
            event_type="page_view",
            event_ts=event_ts,
            path="/",
        )
        sessions = (
            db.query(BehaviourSession)
            .filter(BehaviourSession.tenant_id == tenant_id)
            .all()
        )
        assert len(sessions) == 2

        duplicate = BehaviourSession(
            tenant_id=tenant_id,
            website_id=website_id,
            environment_id=environment_id,
            session_id=session_id,
            started_at=event_ts,
            last_seen_at=event_ts,
            event_count=1,
            page_views=1,
        )
        db.add(duplicate)
        try:
            db.commit()
            raise AssertionError("Expected IntegrityError for duplicate session")
        except IntegrityError:
            db.rollback()
