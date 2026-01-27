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
from app.jobs.revenue_leak import run_revenue_leak_job
from app.models.behaviour_events import BehaviourEvent
from app.models.revenue_impact import ConversionMetric
from app.models.revenue_leaks import RevenueLeakEstimate
from app.models.trust_scoring import TrustSnapshot


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


def _seed_behaviour_event(
    db,
    *,
    tenant_id: int,
    website_id: int,
    env_id: int,
    path: str,
    event_type: str,
    session_id: str,
    event_ts: datetime,
):
    db.add(
        BehaviourEvent(
            tenant_id=tenant_id,
            website_id=website_id,
            environment_id=env_id,
            ingested_at=event_ts,
            event_ts=event_ts,
            event_id=f"{session_id}-{event_type}",
            event_type=event_type,
            url=f"https://example.com{path}",
            path=path,
            referrer=None,
            session_id=session_id,
            visitor_id=None,
            ip_hash=None,
            user_agent="ua",
            meta={},
        )
    )


def _seed_snapshot(
    db,
    *,
    tenant_id: int,
    website_id: int,
    env_id: int,
    path: str,
    bucket_start: datetime,
    trust_score: int,
    factor_count: int,
):
    db.add(
        TrustSnapshot(
            tenant_id=tenant_id,
            website_id=website_id,
            environment_id=env_id,
            bucket_start=bucket_start,
            path=path,
            trust_score=trust_score,
            confidence=0.7,
            factor_count=factor_count,
            created_at=bucket_start,
        )
    )


def test_revenue_leak_job_creates_estimates_for_funnel_paths():
    db_url = f"sqlite:///./revenue_leak_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    bucket_start = datetime.utcnow().replace(minute=0, second=0, microsecond=0)

    with SessionLocal() as db:
        tenant = create_tenant(db, name="Tenant A")
        website = create_website(db, tenant.id, "example.com")
        env = list_environments(db, website.id)[0]

        _seed_snapshot(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            env_id=env.id,
            path="/checkout",
            bucket_start=bucket_start,
            trust_score=60,
            factor_count=2,
        )

        for idx in range(10):
            _seed_behaviour_event(
                db,
                tenant_id=tenant.id,
                website_id=website.id,
                env_id=env.id,
                path="/checkout",
                event_type="page_view",
                session_id=f"s{idx}",
                event_ts=bucket_start + timedelta(minutes=5),
            )
        for idx in range(2):
            _seed_behaviour_event(
                db,
                tenant_id=tenant.id,
                website_id=website.id,
                env_id=env.id,
                path="/checkout",
                event_type="form_submit",
                session_id=f"s{idx}",
                event_ts=bucket_start + timedelta(minutes=10),
            )
        db.commit()

        updated = run_revenue_leak_job(db, lookback_hours=6)
        assert updated >= 1
        estimate = (
            db.query(RevenueLeakEstimate)
            .filter(
                RevenueLeakEstimate.tenant_id == tenant.id,
                RevenueLeakEstimate.path == "/checkout",
            )
            .first()
        )
        assert estimate is not None
        assert estimate.sessions_in_bucket == 10
        assert estimate.observed_conversions == 2


def test_leak_estimate_lost_revenue_calculation_correct():
    db_url = f"sqlite:///./revenue_leak_calc_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    bucket_start = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    baseline_window = bucket_start - timedelta(days=1)

    with SessionLocal() as db:
        tenant = create_tenant(db, name="Tenant A")
        website = create_website(db, tenant.id, "example.com")
        env = list_environments(db, website.id)[0]

        _seed_snapshot(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            env_id=env.id,
            path="/checkout",
            bucket_start=bucket_start,
            trust_score=55,
            factor_count=3,
        )

        for idx in range(10):
            _seed_behaviour_event(
                db,
                tenant_id=tenant.id,
                website_id=website.id,
                env_id=env.id,
                path="/checkout",
                event_type="page_view",
                session_id=f"s{idx}",
                event_ts=bucket_start + timedelta(minutes=2),
            )
        for idx in range(2):
            _seed_behaviour_event(
                db,
                tenant_id=tenant.id,
                website_id=website.id,
                env_id=env.id,
                path="/checkout",
                event_type="form_submit",
                session_id=f"s{idx}",
                event_ts=bucket_start + timedelta(minutes=3),
            )

        db.add(
            ConversionMetric(
                tenant_id=tenant.id,
                website_id=website.id,
                environment_id=env.id,
                metric_key="funnel:/checkout",
                window_start=baseline_window,
                window_end=baseline_window + timedelta(hours=1),
                sessions=100,
                conversions=50,
                conversion_rate=0.5,
                revenue_per_conversion=100.0,
                captured_at=baseline_window + timedelta(hours=1),
            )
        )
        db.commit()

        run_revenue_leak_job(db, lookback_hours=6)
        estimate = (
            db.query(RevenueLeakEstimate)
            .filter(RevenueLeakEstimate.tenant_id == tenant.id)
            .first()
        )
        assert estimate is not None
        assert round(estimate.lost_conversions, 1) == 3.0
        assert round(estimate.estimated_lost_revenue or 0.0, 1) == 300.0


def test_leak_confidence_increases_with_low_trust_score_overlap():
    db_url = f"sqlite:///./revenue_leak_conf_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    bucket_start = datetime.utcnow().replace(minute=0, second=0, microsecond=0)

    with SessionLocal() as db:
        tenant = create_tenant(db, name="Tenant A")
        website = create_website(db, tenant.id, "example.com")
        env = list_environments(db, website.id)[0]

        _seed_snapshot(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            env_id=env.id,
            path="/checkout",
            bucket_start=bucket_start,
            trust_score=40,
            factor_count=4,
        )
        _seed_snapshot(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            env_id=env.id,
            path="/pricing",
            bucket_start=bucket_start,
            trust_score=85,
            factor_count=0,
        )

        for idx in range(10):
            _seed_behaviour_event(
                db,
                tenant_id=tenant.id,
                website_id=website.id,
                env_id=env.id,
                path="/checkout",
                event_type="page_view",
                session_id=f"c{idx}",
                event_ts=bucket_start + timedelta(minutes=5),
            )
            _seed_behaviour_event(
                db,
                tenant_id=tenant.id,
                website_id=website.id,
                env_id=env.id,
                path="/pricing",
                event_type="page_view",
                session_id=f"p{idx}",
                event_ts=bucket_start + timedelta(minutes=6),
            )
        for idx in range(2):
            _seed_behaviour_event(
                db,
                tenant_id=tenant.id,
                website_id=website.id,
                env_id=env.id,
                path="/checkout",
                event_type="form_submit",
                session_id=f"c{idx}",
                event_ts=bucket_start + timedelta(minutes=7),
            )
            _seed_behaviour_event(
                db,
                tenant_id=tenant.id,
                website_id=website.id,
                env_id=env.id,
                path="/pricing",
                event_type="form_submit",
                session_id=f"p{idx}",
                event_ts=bucket_start + timedelta(minutes=8),
            )
        db.commit()

        run_revenue_leak_job(db, lookback_hours=6)
        low_trust = (
            db.query(RevenueLeakEstimate)
            .filter(RevenueLeakEstimate.path == "/checkout")
            .first()
        )
        high_trust = (
            db.query(RevenueLeakEstimate)
            .filter(RevenueLeakEstimate.path == "/pricing")
            .first()
        )
        assert low_trust is not None
        assert high_trust is not None
        assert low_trust.confidence > high_trust.confidence
