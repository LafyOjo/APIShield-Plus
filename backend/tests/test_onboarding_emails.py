import os
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("SKIP_MIGRATIONS", "1")

from app.core.db import Base
import app.core.db as db_module
import app.core.access_log as access_log_module
import app.core.policy as policy_module
from app.core.security import get_password_hash
from app.core.onboarding_emails import queue_first_event_email, run_no_events_nudge_job
from app.crud.memberships import create_membership
from app.crud.tenants import create_tenant
from app.crud.users import create_user
from app.crud.websites import create_website
from app.crud.website_environments import list_environments
from app.crud.behaviour_events import create_behaviour_event
from app.models.email_queue import EmailQueue
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
    return SessionLocal


def test_email_trigger_no_events_after_2h_queues_email_once(tmp_path):
    db_url = f"sqlite:///{tmp_path}/onboarding_emails_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        user = create_user(
            db,
            username="owner-no-events@example.com",
            password_hash=get_password_hash("pw"),
            role="user",
        )
        tenant = create_tenant(db, name="No Events Tenant")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=user.id,
            role=RoleEnum.OWNER,
            created_by_user_id=user.id,
        )
        tenant.created_at = datetime.utcnow() - timedelta(hours=3)
        db.commit()

        queued = run_no_events_nudge_job(db, now=datetime.utcnow(), threshold_hours=2)
        assert queued == 1
        assert db.query(EmailQueue).count() == 1

        queued_again = run_no_events_nudge_job(db, now=datetime.utcnow(), threshold_hours=2)
        assert queued_again == 0
        assert db.query(EmailQueue).count() == 1


def test_email_trigger_first_event_queues_map_wow_email(tmp_path):
    db_url = f"sqlite:///{tmp_path}/onboarding_first_event_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        user = create_user(
            db,
            username="owner-first-event@example.com",
            password_hash=get_password_hash("pw"),
            role="user",
        )
        tenant = create_tenant(db, name="First Event Tenant")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=user.id,
            role=RoleEnum.OWNER,
            created_by_user_id=user.id,
        )
        website = create_website(db, tenant.id, "first-event.example.com", created_by_user_id=user.id)
        env_id = list_environments(db, website.id)[0].id
        create_behaviour_event(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            environment_id=env_id,
            event_id="evt_1",
            event_type="page_view",
            url="https://first-event.example.com/",
            event_ts=datetime.utcnow(),
            path="/",
            referrer=None,
            session_id="s_1",
            visitor_id=None,
            meta={},
        )

        queued = queue_first_event_email(db, tenant_id=tenant.id)
        assert queued is True
        record = db.query(EmailQueue).first()
        assert record is not None
        assert record.template_key == "first_event_map_wow"
