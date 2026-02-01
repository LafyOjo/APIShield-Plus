import os
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("INTEGRATION_ENCRYPTION_KEY", "a" * 32)
os.environ.setdefault("SKIP_MIGRATIONS", "1")

from app.main import app
import app.core.db as db_module
import app.core.access_log as access_log_module
import app.core.policy as policy_module
from app.core.db import Base
from app.core.security import get_password_hash
from app.core.time import utcnow
from app.crud.memberships import create_membership
from app.crud.tenants import create_tenant
from app.crud.users import create_user
from app.crud.websites import create_website
from app.marketplace.catalog import ensure_catalog_seeded
from app.models.enums import RoleEnum
from app.models.incidents import Incident
from app.models.marketplace import MarketplaceTemplate, TemplateImportEvent
from app.models.remediation_playbooks import RemediationPlaybook


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
    Base.metadata.create_all(bind=engine)
    return SessionLocal


def _login(username: str) -> str:
    resp = client.post("/login", json={"username": username, "password": "pw"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _setup_env(SessionLocal, *, username: str, tenant_name: str):
    with SessionLocal() as db:
        owner = create_user(db, username=username, password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name=tenant_name)
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=owner.id,
            role=RoleEnum.OWNER,
            created_by_user_id=owner.id,
        )
        website = create_website(db, tenant.id, f"{tenant.slug}.example.com", created_by_user_id=owner.id)
        db.commit()
        return tenant.slug, tenant.id, website.id, owner.id


def test_template_import_creates_tenant_owned_copy():
    db_url = f"sqlite:///./marketplace_import_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_slug, tenant_id, website_id, user_id = _setup_env(
        SessionLocal,
        username="marketplace",
        tenant_name="Marketplace",
    )

    with SessionLocal() as db:
        incident = Incident(
            tenant_id=tenant_id,
            website_id=website_id,
            status="open",
            category="login",
            title="Credential stuffing spike",
            severity="high",
            first_seen_at=utcnow(),
            last_seen_at=utcnow(),
        )
        db.add(incident)
        db.commit()
        db.refresh(incident)
        ensure_catalog_seeded(db)
        template = (
            db.query(MarketplaceTemplate)
            .filter(MarketplaceTemplate.template_type == "playbook", MarketplaceTemplate.status == "published")
            .first()
        )
        assert template is not None
        template_id = template.id
        incident_id = incident.id

    token = _login("marketplace")
    resp = client.post(
        f"/api/v1/marketplace/templates/{template_id}/import",
        json={"incident_id": incident_id},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["template_id"] == template_id
    assert payload["playbook_id"] is not None

    with SessionLocal() as db:
        playbook = (
            db.query(RemediationPlaybook)
            .filter(RemediationPlaybook.tenant_id == tenant_id, RemediationPlaybook.incident_id == incident_id)
            .first()
        )
        assert playbook is not None
        event = (
            db.query(TemplateImportEvent)
            .filter(TemplateImportEvent.tenant_id == tenant_id, TemplateImportEvent.template_id == template_id)
            .first()
        )
        assert event is not None


def test_unapproved_templates_not_visible_to_non_admins():
    db_url = f"sqlite:///./marketplace_visibility_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_slug, tenant_id, website_id, user_id = _setup_env(
        SessionLocal,
        username="marketplace-visibility",
        tenant_name="MarketplaceVisibility",
    )

    with SessionLocal() as db:
        draft = MarketplaceTemplate(
            template_type="playbook",
            title="Draft template",
            description="Unapproved template",
            stack_type="custom",
            tags=["draft"],
            content_json={"sections": [{"title": "Draft", "steps": ["Step 1"]}]},
            author_user_id=user_id,
            source="community",
            status="draft",
        )
        db.add(draft)
        db.commit()

    token = _login("marketplace-visibility")
    resp = client.get(
        "/api/v1/marketplace/templates",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert all(item["title"] != "Draft template" for item in payload)
