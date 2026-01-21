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
from app.insights.prescriptions import generate_prescriptions
from app.models.incidents import Incident


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


def _create_incident(
    *,
    tenant_id: int,
    website_id: int,
    env_id: int,
    category: str,
    severity: str,
    evidence_json: dict,
):
    now = datetime(2026, 1, 20, 9, 0, 0)
    return Incident(
        tenant_id=tenant_id,
        website_id=website_id,
        environment_id=env_id,
        status="open",
        category=category,
        title="Incident",
        summary=None,
        severity=severity,
        first_seen_at=now,
        last_seen_at=now + timedelta(hours=1),
        primary_ip_hash=None,
        primary_country_code=None,
        evidence_json=evidence_json,
    )


def test_prescription_engine_outputs_templates_for_credential_stuffing():
    db_url = f"sqlite:///./prescriptions_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    with SessionLocal() as db:
        tenant = create_tenant(db, name="Tenant A")
        website = create_website(db, tenant.id, "example.com")
        env = list_environments(db, website.id)[0]

        incident = _create_incident(
            tenant_id=tenant.id,
            website_id=website.id,
            env_id=env.id,
            category="threat",
            severity="high",
            evidence_json={
                "event_types": {"credential_stuffing": 12},
                "request_paths": {"/login": 12},
                "counts": {"security_events": 12},
            },
        )
        db.add(incident)
        db.commit()

        bundle = generate_prescriptions(db, incident=incident, impact_estimate=None)
        db.commit()

        action_ids = {item["id"] for item in bundle.items_json}
        assert "credential_stuffing_mitigation" in action_ids
        assert incident.prescription_bundle_id == str(bundle.id)


def test_prescription_engine_outputs_csp_hardening_for_integrity_incident():
    db_url = f"sqlite:///./prescriptions_csp_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    with SessionLocal() as db:
        tenant = create_tenant(db, name="Tenant A")
        website = create_website(db, tenant.id, "example.com")
        env = list_environments(db, website.id)[0]

        incident = _create_incident(
            tenant_id=tenant.id,
            website_id=website.id,
            env_id=env.id,
            category="integrity",
            severity="medium",
            evidence_json={
                "event_types": {"csp_violation": 4},
                "request_paths": {"/checkout": 4},
                "counts": {"security_events": 4},
            },
        )
        db.add(incident)
        db.commit()

        bundle = generate_prescriptions(db, incident=incident, impact_estimate=None)
        db.commit()

        action_ids = {item["id"] for item in bundle.items_json}
        assert "csp_hardening" in action_ids


def test_prescriptions_include_evidence_links():
    db_url = f"sqlite:///./prescriptions_evidence_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    with SessionLocal() as db:
        tenant = create_tenant(db, name="Tenant A")
        website = create_website(db, tenant.id, "example.com")
        env = list_environments(db, website.id)[0]

        incident = _create_incident(
            tenant_id=tenant.id,
            website_id=website.id,
            env_id=env.id,
            category="integrity",
            severity="medium",
            evidence_json={
                "event_types": {"script_injection_detected": 2},
                "request_paths": {"/checkout": 2},
                "counts": {"security_events": 2},
            },
        )
        db.add(incident)
        db.commit()

        bundle = generate_prescriptions(db, incident=incident, impact_estimate=None)
        db.commit()

        assert bundle.items_json
        first_item = bundle.items_json[0]
        evidence = first_item.get("evidence_links")
        assert evidence is not None
        assert "/checkout" in evidence.get("paths", [])
        assert evidence.get("event_counts", {}).get("script_injection_detected") == 2
