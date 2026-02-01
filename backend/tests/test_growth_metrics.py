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
from app.crud.websites import create_website
from app.crud.website_environments import list_environments
from app.jobs.growth_metrics import run_growth_metrics_job
from app.models.audit_logs import AuditLog
from app.models.behaviour_events import BehaviourEvent
from app.models.growth_metrics import GrowthSnapshot
from app.models.subscriptions import Subscription
from app.models.plans import Plan


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


def _seed_event(db, tenant_id: int, when: datetime):
    website = create_website(db, tenant_id, f"site-{tenant_id}.example.com")
    env = list_environments(db, website.id)[0]
    db.add(
        BehaviourEvent(
            tenant_id=tenant_id,
            website_id=website.id,
            environment_id=env.id,
            ingested_at=when,
            event_ts=when,
            event_id=f"event-{tenant_id}-{when.timestamp()}",
            event_type="page_view",
            url="https://example.com",
            path="/",
            session_id="s1",
            meta={},
        )
    )


def test_growth_metrics_snapshot_excludes_demo_tenants():
    db_url = f"sqlite:///./growth_demo_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    now = datetime.utcnow()

    with SessionLocal() as db:
        demo = create_tenant(db, name="Demo Co")
        demo.is_demo_mode = True
        real = create_tenant(db, name="Real Co")
        db.commit()

        _seed_event(db, real.id, now)
        _seed_event(db, demo.id, now)
        db.commit()

        snapshot = run_growth_metrics_job(db, snapshot_date=now.date(), lookback_days=1)
        assert isinstance(snapshot, GrowthSnapshot)
        assert snapshot.signups == 1
        assert snapshot.activated == 1


def test_cohort_calculation_correct_week_bucketing():
    db_url = f"sqlite:///./growth_cohort_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    now = datetime.utcnow()

    with SessionLocal() as db:
        tenant_a = create_tenant(db, name="Week A")
        tenant_b = create_tenant(db, name="Week B")
        tenant_a.created_at = now - timedelta(days=10)
        tenant_b.created_at = now - timedelta(days=2)
        plan = Plan(name="Free", is_active=True)
        db.add(plan)
        db.commit()

        _seed_event(db, tenant_a.id, now)
        db.add(
            Subscription(
                tenant_id=tenant_b.id,
                plan_id=plan.id,
                plan_key="pro",
                status="active",
                provider="manual",
            )
        )
        db.commit()

        snapshot = run_growth_metrics_job(db, snapshot_date=now.date(), lookback_days=1)
        cohorts = snapshot.cohort_json
        assert cohorts
        weeks = {entry["week_start"] for entry in cohorts}
        assert len(weeks) >= 2


def test_upgrade_conversion_attributed_to_paywall_event():
    db_url = f"sqlite:///./growth_paywall_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    now = datetime.utcnow()

    with SessionLocal() as db:
        tenant = create_tenant(db, name="Paywall Co")
        db.add(
            AuditLog(
                tenant_id=tenant.id,
                username="ops@example.com",
                event="paywall.checkout_started:geo_map:security_map_range",
                timestamp=now - timedelta(hours=1),
            )
        )
        db.add(
            AuditLog(
                tenant_id=tenant.id,
                username="ops@example.com",
                event="billing.checkout.completed:pro",
                timestamp=now,
            )
        )
        db.commit()

        snapshot = run_growth_metrics_job(db, snapshot_date=now.date(), lookback_days=1)
        paywall = snapshot.paywall_json
        assert paywall
        matched = next((row for row in paywall if row["feature_key"] == "geo_map"), None)
        assert matched is not None
        assert matched.get("upgrades") == 1
