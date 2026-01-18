import os
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ["SKIP_MIGRATIONS"] = "1"

from app.main import app
import app.core.db as db_module
import app.core.access_log as access_log_module
import app.core.policy as policy_module
from app.core.config import settings
from app.core.db import Base
from app.core.security import get_password_hash
from app.crud.api_keys import create_api_key
from app.crud.domain_verification import create_verification
from app.crud.memberships import create_membership
from app.crud.tenants import create_tenant
from app.crud.users import create_user
from app.crud.website_environments import list_environments
from app.crud.websites import create_website
from app.models.enums import RoleEnum


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


def test_install_endpoint_requires_owner_or_admin():
    db_url = f"sqlite:///./install_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="install-owner", password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name="InstallTenant")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=owner.id,
            role=RoleEnum.OWNER,
            created_by_user_id=owner.id,
        )
        viewer = create_user(db, username="install-viewer", password_hash=get_password_hash("pw"), role="user")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=viewer.id,
            role=RoleEnum.VIEWER,
            created_by_user_id=owner.id,
        )
        website = create_website(db, tenant.id, "install.example.com", created_by_user_id=owner.id)
        tenant_slug = tenant.slug
        website_id = website.id

    token = _login("install-viewer")
    resp = client.get(
        f"/api/v1/websites/{website_id}/install",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    expected = 404 if settings.TENANT_STRICT_404 else 403
    assert resp.status_code == expected


def test_install_endpoint_tenant_scoped():
    db_url = f"sqlite:///./install_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        user = create_user(db, username="install-cross", password_hash=get_password_hash("pw"), role="user")
        tenant_a = create_tenant(db, name="InstallTenantA")
        tenant_b = create_tenant(db, name="InstallTenantB")
        create_membership(
            db,
            tenant_id=tenant_a.id,
            user_id=user.id,
            role=RoleEnum.OWNER,
            created_by_user_id=user.id,
        )
        website = create_website(db, tenant_b.id, "cross-install.example.com", created_by_user_id=user.id)
        tenant_a_slug = tenant_a.slug
        website_id = website.id

    token = _login("install-cross")
    resp = client.get(
        f"/api/v1/websites/{website_id}/install",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_a_slug},
    )
    assert resp.status_code == 404


def test_install_endpoint_does_not_return_secret_hash():
    db_url = f"sqlite:///./install_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="install-safe", password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name="InstallSafe")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=owner.id,
            role=RoleEnum.OWNER,
            created_by_user_id=owner.id,
        )
        website = create_website(db, tenant.id, "safe-install.example.com", created_by_user_id=owner.id)
        environment = list_environments(db, website.id)[0]
        create_api_key(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            environment_id=environment.id,
            name="Install Key",
            created_by_user_id=owner.id,
        )
        create_verification(db, tenant.id, website.id, "meta_tag", created_by_user_id=owner.id)
        tenant_slug = tenant.slug
        website_id = website.id

    token = _login("install-safe")
    resp = client.get(
        f"/api/v1/websites/{website_id}/install",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert "raw_secret" not in str(payload).lower()
    assert "secret_hash" not in str(payload).lower()
    assert payload["environments"]
    env = payload["environments"][0]
    assert env["keys"]
    key = env["keys"][0]
    assert key["public_key"]
    assert key["snippet"]
    assert key["public_key"] in key["snippet"]
