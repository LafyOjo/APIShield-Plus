import os
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ["SKIP_MIGRATIONS"] = "1"

from app.main import app
import app.core.access_log as access_log_module
import app.core.db as db_module
import app.core.policy as policy_module
from app.core.security import get_password_hash
from app.crud.memberships import create_membership
from app.crud.subscriptions import set_tenant_plan
from app.crud.tenants import create_tenant
from app.crud.users import create_user
from app.crud.website_environments import list_environments
from app.crud.websites import create_website
from app.models.enums import RoleEnum
from app.models.incidents import Incident, IncidentRecovery, IncidentSecurityEventLink
from app.models.plans import Plan
from app.models.prescriptions import PrescriptionBundle, PrescriptionItem
from app.models.revenue_impact import ImpactEstimate
from app.models.security_events import SecurityEvent


client = TestClient(app)


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
    db_module.Base.metadata.create_all(bind=engine)
    return SessionLocal


def _login(username: str, tenant_slug: str) -> str:
    resp = client.post(
        "/login",
        json={"username": username, "password": "pw"},
        headers={"X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _seed_plan(db, *, name: str, geo_granularity: str | None = None, geo_enabled: bool = True) -> Plan:
    limits = {}
    if geo_granularity:
        limits["geo_granularity"] = geo_granularity
    plan = Plan(
        name=name,
        price_monthly=0,
        limits_json=limits,
        features_json={"geo_map": geo_enabled},
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def _seed_tenant(SessionLocal, *, username: str, tenant_name: str, domain: str, plan: Plan | None = None):
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
        env = list_environments(db, website.id)[0]
        if plan:
            set_tenant_plan(db, tenant.id, plan.id)
        db.commit()
        return tenant.slug, tenant.id, website.id, env.id


def _seed_incident(db, *, tenant_id: int, website_id: int, env_id: int, title: str):
    now = datetime.utcnow()
    incident = Incident(
        tenant_id=tenant_id,
        website_id=website_id,
        environment_id=env_id,
        status="open",
        category="login",
        title=title,
        summary=None,
        severity="medium",
        first_seen_at=now - timedelta(hours=2),
        last_seen_at=now - timedelta(hours=1),
        evidence_json={
            "event_types": {"login_attempt_failed": 3},
            "request_paths": {"/login": 3},
            "counts": {"security_events": 3},
        },
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident


def test_incident_report_redacts_raw_ip():
    db_url = f"sqlite:///./incident_report_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        plan = _seed_plan(db, name="GeoCountry", geo_granularity="country")
        tenant_slug, tenant_id, website_id, env_id = _seed_tenant(
            SessionLocal,
            username="alice",
            tenant_name="Acme",
            domain="a.example.com",
            plan=plan,
        )
        incident = _seed_incident(
            db,
            tenant_id=tenant_id,
            website_id=website_id,
            env_id=env_id,
            title="Login spike",
        )
        incident_id = incident.id
        event = SecurityEvent(
            tenant_id=tenant_id,
            website_id=website_id,
            environment_id=env_id,
            category="login",
            event_type="login_attempt_failed",
            severity="medium",
            source="server",
            request_path="/login",
            client_ip="203.0.113.5",
            ip_hash="hash123",
            country_code="US",
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        db.add(
            IncidentSecurityEventLink(
                incident_id=incident_id,
                security_event_id=event.id,
            )
        )
        db.commit()

    token = _login("alice", tenant_slug)
    resp = client.get(
        f"/api/v1/incidents/{incident_id}/report?format=json",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    assert "203.0.113.5" not in resp.text


def test_incident_report_respects_entitlements_for_geo_asn_detail():
    db_url = f"sqlite:///./incident_report_geo_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        plan = _seed_plan(db, name="GeoCountryOnly", geo_granularity="country")
        tenant_slug, tenant_id, website_id, env_id = _seed_tenant(
            SessionLocal,
            username="bob",
            tenant_name="Umbrella",
            domain="b.example.com",
            plan=plan,
        )
        incident = _seed_incident(
            db,
            tenant_id=tenant_id,
            website_id=website_id,
            env_id=env_id,
            title="Credential stuffing",
        )
        incident_id = incident.id
        event = SecurityEvent(
            tenant_id=tenant_id,
            website_id=website_id,
            environment_id=env_id,
            category="login",
            event_type="credential_stuffing",
            severity="high",
            source="server",
            request_path="/login",
            ip_hash="hash456",
            country_code="US",
            asn_number=64500,
            asn_org="ExampleNet",
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        db.add(
            IncidentSecurityEventLink(
                incident_id=incident_id,
                security_event_id=event.id,
            )
        )
        db.commit()

    token = _login("bob", tenant_slug)
    resp = client.get(
        f"/api/v1/incidents/{incident_id}/report?format=json",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["evidence"]["countries"]
    assert payload["evidence"]["asns"] == []


def test_incident_report_contains_prescription_statuses_and_recovery():
    db_url = f"sqlite:///./incident_report_recovery_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        tenant_slug, tenant_id, website_id, env_id = _seed_tenant(
            SessionLocal,
            username="carol",
            tenant_name="Wayne",
            domain="c.example.com",
        )
        incident = _seed_incident(
            db,
            tenant_id=tenant_id,
            website_id=website_id,
            env_id=env_id,
            title="Checkout issue",
        )
        incident_id = incident.id
        impact = ImpactEstimate(
            tenant_id=tenant_id,
            website_id=website_id,
            environment_id=env_id,
            metric_key="checkout_conversion",
            window_start=incident.first_seen_at,
            window_end=incident.last_seen_at,
            observed_rate=0.08,
            baseline_rate=0.15,
            delta_rate=-0.07,
            estimated_lost_conversions=12,
            estimated_lost_revenue=2400.0,
            confidence=0.6,
        )
        db.add(impact)
        db.commit()
        db.refresh(impact)
        incident.impact_estimate_id = impact.id

        bundle = PrescriptionBundle(
            tenant_id=tenant_id,
            website_id=website_id,
            environment_id=env_id,
            incident_id=incident_id,
            status="suggested",
            items_json=[
                {
                    "id": "login_hardening",
                    "why_it_matters": "Protect logins",
                    "steps": ["Enable MFA"],
                }
            ],
        )
        db.add(bundle)
        db.commit()
        db.refresh(bundle)
        db.add(
            PrescriptionItem(
                bundle_id=bundle.id,
                tenant_id=tenant_id,
                website_id=website_id,
                environment_id=env_id,
                incident_id=incident_id,
                key="login_hardening",
                title="Harden login protections",
                priority="P1",
                effort="med",
                expected_effect="security",
                status="applied",
                notes="Applied MFA",
            )
        )
        incident.prescription_bundle_id = str(bundle.id)

        recovery = IncidentRecovery(
            tenant_id=tenant_id,
            website_id=website_id,
            environment_id=env_id,
            incident_id=incident_id,
            measured_at=incident.last_seen_at + timedelta(hours=4),
            window_start=incident.last_seen_at,
            window_end=incident.last_seen_at + timedelta(hours=4),
            post_conversion_rate=0.14,
            change_in_errors=-0.2,
            change_in_threats=-0.3,
            recovery_ratio=0.8,
            confidence=0.7,
        )
        db.add(recovery)
        db.commit()

    token = _login("carol", tenant_slug)
    resp = client.get(
        f"/api/v1/incidents/{incident_id}/report?format=json",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    statuses = [item["status"] for item in payload["prescriptions"]]
    assert "applied" in statuses
    assert payload["recovery"]["recovery_ratio"] == 0.8
