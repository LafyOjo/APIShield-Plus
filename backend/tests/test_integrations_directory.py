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
from app.crud.memberships import create_membership
from app.crud.tenants import create_tenant
from app.crud.users import create_user
from app.crud.websites import create_website
from app.crud.website_stack_profiles import set_stack_manual_override
from app.models.enums import RoleEnum
from app.models.integration_directory import IntegrationInstallEvent


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
        return tenant.slug, tenant.id, website.id


def test_integration_install_event_logged_on_copy_snippet():
    db_url = f"sqlite:///./integrations_install_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_slug, tenant_id, website_id = _setup_env(SessionLocal, username="integrations", tenant_name="Integrations")

    token = _login("integrations")
    resp = client.post(
        "/api/v1/integrations/install-events",
        json={
            "integration_key": "wordpress-plugin",
            "website_id": website_id,
            "method": "copy",
            "metadata": {"source": "directory"},
        },
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["integration_key"] == "wordpress-plugin"

    with SessionLocal() as db:
        events = db.query(IntegrationInstallEvent).filter(IntegrationInstallEvent.tenant_id == tenant_id).all()
        assert len(events) == 1
        assert events[0].method == "copy"


def test_integrations_recommended_filter_uses_stack_profile():
    db_url = f"sqlite:///./integrations_reco_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_slug, tenant_id, website_id = _setup_env(SessionLocal, username="integrations-reco", tenant_name="IntegrationsReco")

    with SessionLocal() as db:
        set_stack_manual_override(db, tenant_id=tenant_id, website_id=website_id, stack_type="wordpress")

    token = _login("integrations-reco")
    resp = client.get(
        f"/api/v1/integrations/directory?website_id={website_id}",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    wordpress = next((item for item in payload if item["key"] == "wordpress-plugin"), None)
    shopify = next((item for item in payload if item["key"] == "shopify-app"), None)
    assert wordpress is not None and wordpress["recommended"] is True
    assert shopify is not None and shopify["recommended"] is False
