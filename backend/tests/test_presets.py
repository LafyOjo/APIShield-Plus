import os
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "secret")

from app.core.db import Base
from app.crud.tenants import create_tenant
from app.crud.websites import create_website
from app.models.incidents import Incident
from app.presets.generator import get_or_generate_presets


def _make_session(tmp_path):
    db_url = f"sqlite:///{tmp_path}/presets.db"
    os.environ["DATABASE_URL"] = db_url
    os.environ["SKIP_MIGRATIONS"] = "1"
    engine = create_engine(db_url, future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal()


def _create_incident(session, *, tenant_id: int, website_id: int, title: str, category: str, evidence: dict):
    now = datetime.utcnow()
    incident = Incident(
        tenant_id=tenant_id,
        website_id=website_id,
        status="open",
        category=category,
        title=title,
        severity="high",
        first_seen_at=now - timedelta(hours=1),
        last_seen_at=now,
        evidence_json=evidence,
    )
    session.add(incident)
    session.commit()
    session.refresh(incident)
    return incident


def test_csp_preset_generated_in_report_only_mode_by_default(tmp_path):
    session = _make_session(tmp_path)
    tenant = create_tenant(session, name="Acme")
    website = create_website(session, tenant.id, "acme.com")
    incident = _create_incident(
        session,
        tenant_id=tenant.id,
        website_id=website.id,
        title="CSP violations detected",
        category="integrity",
        evidence={"event_types": {"csp_violation": 3}},
    )

    presets = get_or_generate_presets(session, incident=incident, website=website)
    csp = next(preset for preset in presets if preset.preset_type == "csp")
    metadata = csp.content_json.get("metadata", {})
    assert metadata.get("report_only") is True
    header_block = csp.content_json.get("formats", {}).get("copy_blocks", [])[0]["content"]
    assert "Content-Security-Policy-Report-Only" in header_block

    session.close()


def test_rate_limit_preset_includes_login_path_when_credential_stuffing(tmp_path):
    session = _make_session(tmp_path)
    tenant = create_tenant(session, name="Umbrella")
    website = create_website(session, tenant.id, "umbrella.com")
    incident = _create_incident(
        session,
        tenant_id=tenant.id,
        website_id=website.id,
        title="Credential stuffing spike",
        category="login",
        evidence={"event_types": {"credential_stuffing": 12}},
    )

    presets = get_or_generate_presets(session, incident=incident, website=website)
    rate_limit = next(preset for preset in presets if preset.preset_type == "rate_limit")
    paths = rate_limit.content_json.get("metadata", {}).get("paths", [])
    assert "/login" in paths

    session.close()


def test_presets_tenant_scoped(tmp_path):
    session = _make_session(tmp_path)
    tenant_a = create_tenant(session, name="Tenant A")
    tenant_b = create_tenant(session, name="Tenant B")
    website_a = create_website(session, tenant_a.id, "tenant-a.com")
    website_b = create_website(session, tenant_b.id, "tenant-b.com")

    incident_a = _create_incident(
        session,
        tenant_id=tenant_a.id,
        website_id=website_a.id,
        title="Login abuse",
        category="login",
        evidence={"event_types": {"credential_stuffing": 5}},
    )
    incident_b = _create_incident(
        session,
        tenant_id=tenant_b.id,
        website_id=website_b.id,
        title="Integrity issue",
        category="integrity",
        evidence={"event_types": {"script_injection": 1}},
    )

    presets_a = get_or_generate_presets(session, incident=incident_a, website=website_a)
    presets_b = get_or_generate_presets(session, incident=incident_b, website=website_b)

    assert all(preset.tenant_id == tenant_a.id for preset in presets_a)
    assert all(preset.tenant_id == tenant_b.id for preset in presets_b)

    session.close()
