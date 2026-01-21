import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("SKIP_MIGRATIONS", "1")

import app.core.db as db_module
from app.core.revenue_impact import compute_baseline, compute_impact
from app.crud.tenants import create_tenant
from app.models.revenue_impact import ImpactEstimate


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


def test_compute_baseline_rolling_average():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    metrics = [
        {
            "window_end": now - timedelta(days=1),
            "sessions": 100,
            "conversions": 10,
            "conversion_rate": 0.1,
        },
        {
            "window_end": now - timedelta(days=3),
            "sessions": 200,
            "conversions": 30,
            "conversion_rate": 0.15,
        },
        {
            "window_end": now - timedelta(days=30),
            "sessions": 500,
            "conversions": 200,
            "conversion_rate": 0.4,
        },
    ]
    baseline = compute_baseline(metrics, window_days=14, now=now)
    assert round(baseline, 6) == round(40 / 300, 6)


def test_compute_impact_estimate_lost_revenue():
    impact = compute_impact(
        observed_rate=0.05,
        baseline_rate=0.1,
        sessions=1000,
        revenue_per_conversion=20.0,
    )
    assert impact["delta_rate"] == 0.05
    assert impact["estimated_lost_conversions"] == 50
    assert impact["estimated_lost_revenue"] == 1000.0


def test_impact_estimate_scoped_to_tenant():
    db_url = f"sqlite:///./impact_estimates_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    with SessionLocal() as db:
        tenant_a = create_tenant(db, name="Tenant A")
        tenant_b = create_tenant(db, name="Tenant B")
        now = datetime.now(timezone.utc)
        db.add(
            ImpactEstimate(
                tenant_id=tenant_a.id,
                metric_key="checkout_conversion",
                window_start=now - timedelta(days=1),
                window_end=now,
                observed_rate=0.05,
                baseline_rate=0.1,
                delta_rate=0.05,
                estimated_lost_conversions=10,
                estimated_lost_revenue=200.0,
                confidence=0.7,
            )
        )
        db.add(
            ImpactEstimate(
                tenant_id=tenant_b.id,
                metric_key="checkout_conversion",
                window_start=now - timedelta(days=1),
                window_end=now,
                observed_rate=0.08,
                baseline_rate=0.1,
                delta_rate=0.02,
                estimated_lost_conversions=4,
                estimated_lost_revenue=80.0,
                confidence=0.5,
            )
        )
        db.commit()

        count_a = (
            db.query(ImpactEstimate)
            .filter(ImpactEstimate.tenant_id == tenant_a.id)
            .count()
        )
        count_b = (
            db.query(ImpactEstimate)
            .filter(ImpactEstimate.tenant_id == tenant_b.id)
            .count()
        )
        assert count_a == 1
        assert count_b == 1
