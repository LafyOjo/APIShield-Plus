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
from app.models.website_stack_profiles import WebsiteStackProfile
from app.playbooks.generator import get_or_generate_playbook


def _make_session(tmp_path):
    db_url = f"sqlite:///{tmp_path}/playbooks.db"
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


def test_playbook_generation_selects_correct_stack_templates(tmp_path):
    session = _make_session(tmp_path)
    tenant = create_tenant(session, name="ShopifyTenant")
    website = create_website(session, tenant.id, "shopify.example")
    stack = WebsiteStackProfile(
        tenant_id=tenant.id,
        website_id=website.id,
        stack_type="shopify",
        confidence=0.9,
        detected_signals_json={},
        manual_override=True,
    )
    session.add(stack)
    session.commit()

    incident = _create_incident(
        session,
        tenant_id=tenant.id,
        website_id=website.id,
        title="Script injection detected",
        category="integrity",
        evidence={"event_types": {"script_injection": 7}},
    )

    playbook = get_or_generate_playbook(session, incident=incident, stack_profile=stack)
    assert playbook is not None
    assert playbook.stack_type == "shopify"
    sections = playbook.sections_json or []
    steps = " ".join(" ".join(section.get("steps", [])) for section in sections)
    assert "theme.liquid" in steps

    session.close()


def test_playbook_contains_verification_and_rollback_sections(tmp_path):
    session = _make_session(tmp_path)
    tenant = create_tenant(session, name="GenericTenant")
    website = create_website(session, tenant.id, "generic.example")

    incident = _create_incident(
        session,
        tenant_id=tenant.id,
        website_id=website.id,
        title="Conversion drop detected",
        category="conversion",
        evidence={"event_types": {"js_error": 12}},
    )

    playbook = get_or_generate_playbook(session, incident=incident, stack_profile=None)
    assert playbook is not None
    sections = playbook.sections_json or []
    assert sections
    for section in sections:
        assert section.get("verification_steps")
        assert section.get("rollback_steps")

    session.close()


def test_playbook_includes_code_snippets_when_applicable(tmp_path):
    session = _make_session(tmp_path)
    tenant = create_tenant(session, name="RateLimitTenant")
    website = create_website(session, tenant.id, "rate.example")
    stack = WebsiteStackProfile(
        tenant_id=tenant.id,
        website_id=website.id,
        stack_type="custom",
        confidence=0.4,
        detected_signals_json={},
        manual_override=False,
    )
    session.add(stack)
    session.commit()

    incident = _create_incident(
        session,
        tenant_id=tenant.id,
        website_id=website.id,
        title="Credential stuffing spike",
        category="login",
        evidence={"event_types": {"credential_stuffing": 25}},
    )

    playbook = get_or_generate_playbook(session, incident=incident, stack_profile=stack)
    assert playbook is not None
    sections = playbook.sections_json or []
    assert any(section.get("code_snippets") for section in sections)

    session.close()
