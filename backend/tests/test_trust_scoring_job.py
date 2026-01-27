import os
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("SKIP_MIGRATIONS", "1")

import app.core.db as db_module
from app.crud.tenants import create_tenant
from app.crud.website_environments import list_environments
from app.crud.websites import create_website
from app.jobs.trust_scoring import run_trust_scoring
from app.models.behaviour_events import BehaviourEvent
from app.models.security_events import SecurityEvent
from app.models.trust_scoring import TrustFactorAgg, TrustSnapshot


def _setup_db(db_url: str):
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        future=True,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db_module.engine = engine
    db_module.SessionLocal = SessionLocal
    db_module.Base.metadata.create_all(bind=engine)
    return SessionLocal


def _seed_security_event(db, *, tenant_id: int, website_id: int, env_id: int, path: str, created_at: datetime):
    db.add(
        SecurityEvent(
            tenant_id=tenant_id,
            website_id=website_id,
            environment_id=env_id,
            created_at=created_at,
            event_ts=created_at,
            category="auth",
            event_type="login_failed",
            severity="high",
            source="server",
            request_path=path,
        )
    )


def _seed_behaviour_error(db, *, tenant_id: int, website_id: int, env_id: int, path: str, ingested_at: datetime):
    db.add(
        BehaviourEvent(
            tenant_id=tenant_id,
            website_id=website_id,
            environment_id=env_id,
            ingested_at=ingested_at,
            event_ts=ingested_at,
            event_id=str(uuid4()),
            event_type="error",
            url=f"https://example.com{path}",
            path=path,
            referrer=None,
            session_id="s1",
            visitor_id=None,
            ip_hash=None,
            user_agent="ua",
            meta={"message": "boom"},
        )
    )


def test_trust_scoring_job_creates_snapshots():
    db_url = f"sqlite:///./trust_snapshots_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    now = datetime.utcnow()
    with SessionLocal() as db:
        tenant = create_tenant(db, name="Tenant A")
        website = create_website(db, tenant.id, "example.com")
        env = list_environments(db, website.id)[0]
        for _ in range(2):
            _seed_security_event(
                db,
                tenant_id=tenant.id,
                website_id=website.id,
                env_id=env.id,
                path="/login",
                created_at=now,
            )
        for _ in range(2):
            _seed_behaviour_error(
                db,
                tenant_id=tenant.id,
                website_id=website.id,
                env_id=env.id,
                path="/checkout",
                ingested_at=now,
            )
        db.commit()

        updated = run_trust_scoring(db, lookback_hours=6)
        assert updated >= 1

        snapshots = db.query(TrustSnapshot).filter(TrustSnapshot.tenant_id == tenant.id).all()
        assert snapshots
        paths = {row.path for row in snapshots}
        assert "/login" in paths or "/checkout" in paths


def test_trust_scoring_job_includes_factors_from_security_and_errors():
    db_url = f"sqlite:///./trust_factors_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    now = datetime.utcnow()
    with SessionLocal() as db:
        tenant = create_tenant(db, name="Tenant A")
        website = create_website(db, tenant.id, "example.com")
        env = list_environments(db, website.id)[0]
        for _ in range(5):
            _seed_security_event(
                db,
                tenant_id=tenant.id,
                website_id=website.id,
                env_id=env.id,
                path="/login",
                created_at=now,
            )
            _seed_behaviour_error(
                db,
                tenant_id=tenant.id,
                website_id=website.id,
                env_id=env.id,
                path="/checkout",
                ingested_at=now,
            )
        db.commit()

        run_trust_scoring(db, lookback_hours=6)
        factors = db.query(TrustFactorAgg).filter(TrustFactorAgg.tenant_id == tenant.id).all()
        factor_types = {row.factor_type for row in factors}
        assert "login_fail_spike" in factor_types
        assert "js_error_spike" in factor_types


def test_trust_scoring_job_scopes_by_tenant():
    db_url = f"sqlite:///./trust_scope_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    now = datetime.utcnow() - timedelta(hours=1)
    with SessionLocal() as db:
        tenant_a = create_tenant(db, name="Tenant A")
        tenant_b = create_tenant(db, name="Tenant B")
        website_a = create_website(db, tenant_a.id, "a.example.com")
        website_b = create_website(db, tenant_b.id, "b.example.com")
        env_a = list_environments(db, website_a.id)[0]
        env_b = list_environments(db, website_b.id)[0]

        for _ in range(2):
            _seed_security_event(
                db,
                tenant_id=tenant_a.id,
                website_id=website_a.id,
                env_id=env_a.id,
                path="/login",
                created_at=now,
            )
            _seed_security_event(
                db,
                tenant_id=tenant_b.id,
                website_id=website_b.id,
                env_id=env_b.id,
                path="/login",
                created_at=now,
            )
        db.commit()

        run_trust_scoring(db, lookback_hours=6)
        count_a = db.query(TrustSnapshot).filter(TrustSnapshot.tenant_id == tenant_a.id).count()
        count_b = db.query(TrustSnapshot).filter(TrustSnapshot.tenant_id == tenant_b.id).count()
        assert count_a >= 1
        assert count_b >= 1
