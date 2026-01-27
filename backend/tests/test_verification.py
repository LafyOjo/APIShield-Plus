import os
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "secret")

from app.core.db import Base
from app.crud.tenants import create_tenant
from app.crud.websites import create_website
from app.models.behaviour_events import BehaviourEvent
from app.models.incidents import Incident
from app.models.revenue_leaks import RevenueLeakEstimate
from app.models.security_events import SecurityEvent
from app.models.trust_scoring import TrustSnapshot
from app.models.website_environments import WebsiteEnvironment
from app.verify.evaluator import evaluate_verification


def _make_session(tmp_path):
    db_url = f"sqlite:///{tmp_path}/verification.db"
    os.environ["DATABASE_URL"] = db_url
    os.environ["SKIP_MIGRATIONS"] = "1"
    engine = create_engine(db_url, future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal()


def _create_incident(session, *, tenant_id: int, website_id: int) -> Incident:
    now = datetime.utcnow()
    incident = Incident(
        tenant_id=tenant_id,
        website_id=website_id,
        status="open",
        category="login",
        title="Credential stuffing spike",
        severity="high",
        first_seen_at=now - timedelta(hours=8),
        last_seen_at=now - timedelta(hours=2),
        evidence_json={"event_types": {"credential_stuffing": 10}},
    )
    session.add(incident)
    session.commit()
    session.refresh(incident)
    return incident


def test_verification_passes_when_threats_drop_and_conversion_recovers(tmp_path):
    session = _make_session(tmp_path)
    tenant = create_tenant(session, name="Acme")
    website = create_website(session, tenant.id, "acme.com")
    environment = (
        session.query(WebsiteEnvironment).filter(WebsiteEnvironment.website_id == website.id).first()
    )
    incident = _create_incident(session, tenant_id=tenant.id, website_id=website.id)

    before_ts = incident.first_seen_at - timedelta(hours=1)
    after_ts = incident.last_seen_at + timedelta(hours=1)

    for _ in range(20):
        session.add(
            SecurityEvent(
                tenant_id=tenant.id,
                website_id=website.id,
                created_at=before_ts,
                category="login",
                event_type="login_failure",
                severity="high",
                source="api",
            )
        )
    for _ in range(5):
        session.add(
            SecurityEvent(
                tenant_id=tenant.id,
                website_id=website.id,
                created_at=after_ts,
                category="login",
                event_type="login_failure",
                severity="medium",
                source="api",
            )
        )

    for _ in range(15):
        session.add(
            BehaviourEvent(
                tenant_id=tenant.id,
                website_id=website.id,
                environment_id=environment.id,
                ingested_at=before_ts,
                event_ts=before_ts,
                event_id=f"evt_before_{_}",
                event_type="js_error",
                url="https://acme.com/checkout",
                path="/checkout",
            )
        )
    for _ in range(5):
        session.add(
            BehaviourEvent(
                tenant_id=tenant.id,
                website_id=website.id,
                environment_id=environment.id,
                ingested_at=after_ts,
                event_ts=after_ts,
                event_id=f"evt_after_{_}",
                event_type="js_error",
                url="https://acme.com/checkout",
                path="/checkout",
            )
        )

    session.add(
        TrustSnapshot(
            tenant_id=tenant.id,
            website_id=website.id,
            environment_id=environment.id,
            bucket_start=before_ts,
            trust_score=50,
            confidence=0.6,
            factor_count=2,
        )
    )
    session.add(
        TrustSnapshot(
            tenant_id=tenant.id,
            website_id=website.id,
            environment_id=environment.id,
            bucket_start=after_ts,
            trust_score=85,
            confidence=0.8,
            factor_count=1,
        )
    )

    session.add(
        RevenueLeakEstimate(
            tenant_id=tenant.id,
            website_id=website.id,
            environment_id=environment.id,
            bucket_start=before_ts,
            path="/checkout",
            baseline_conversion_rate=0.3,
            observed_conversion_rate=0.1,
            sessions_in_bucket=100,
            expected_conversions=30,
            observed_conversions=10,
            lost_conversions=20,
            revenue_per_conversion=100,
            estimated_lost_revenue=2000,
            confidence=0.7,
        )
    )
    session.add(
        RevenueLeakEstimate(
            tenant_id=tenant.id,
            website_id=website.id,
            environment_id=environment.id,
            bucket_start=after_ts,
            path="/checkout",
            baseline_conversion_rate=0.3,
            observed_conversion_rate=0.28,
            sessions_in_bucket=90,
            expected_conversions=27,
            observed_conversions=25,
            lost_conversions=2,
            revenue_per_conversion=100,
            estimated_lost_revenue=200,
            confidence=0.8,
        )
    )

    session.commit()

    run = evaluate_verification(session, incident=incident, before_hours=24, after_hours=6)
    assert run.status in {"passed", "failed"}
    assert any(check["status"] == "passed" for check in run.checks_json)

    session.close()


def test_verification_inconclusive_when_no_data(tmp_path):
    session = _make_session(tmp_path)
    tenant = create_tenant(session, name="Umbrella")
    website = create_website(session, tenant.id, "umbrella.com")
    incident = _create_incident(session, tenant_id=tenant.id, website_id=website.id)

    run = evaluate_verification(session, incident=incident, before_hours=24, after_hours=6)
    assert run.status == "inconclusive"
    assert all(check["status"] == "inconclusive" for check in run.checks_json)

    session.close()
