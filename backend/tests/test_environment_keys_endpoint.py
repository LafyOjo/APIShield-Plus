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
        environment = list_environments(db, website.id)[0]
        db.commit()
        return tenant.slug, environment.id


def test_create_key_returns_public_key_and_snippet(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY_SECRET_RETURN_IN_RESPONSE", True)
    db_url = f"sqlite:///./env_keys_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_slug, env_id = _setup_env(SessionLocal, username="env-key", tenant_name="EnvKeyTenant")

    token = _login("env-key")
    resp = client.post(
        f"/api/v1/environments/{env_id}/keys",
        json={"name": "Staging Key"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["public_key"]
    assert payload["snippet"]
    assert payload["public_key"] in payload["snippet"]
    assert settings.AGENT_URL in payload["snippet"]
    assert payload["raw_secret"]


def test_create_key_cross_tenant_env_rejected():
    db_url = f"sqlite:///./env_keys_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_a_slug, _env_a = _setup_env(SessionLocal, username="env-cross", tenant_name="EnvCrossA")
    _tenant_b_slug, env_b_id = _setup_env(SessionLocal, username="env-cross-b", tenant_name="EnvCrossB")

    token = _login("env-cross")
    resp = client.post(
        f"/api/v1/environments/{env_b_id}/keys",
        json={"name": "Cross Key"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_a_slug},
    )
    assert resp.status_code == 404


def test_secret_returned_only_once_and_only_in_dev_mode(monkeypatch):
    db_url = f"sqlite:///./env_keys_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_slug, env_id = _setup_env(SessionLocal, username="env-secret", tenant_name="EnvSecretTenant")

    token = _login("env-secret")
    monkeypatch.setattr(settings, "API_KEY_SECRET_RETURN_IN_RESPONSE", False)
    resp = client.post(
        f"/api/v1/environments/{env_id}/keys",
        json={"name": "Prod Key"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    assert resp.json()["raw_secret"] is None

    monkeypatch.setattr(settings, "API_KEY_SECRET_RETURN_IN_RESPONSE", True)
    resp = client.post(
        f"/api/v1/environments/{env_id}/keys",
        json={"name": "Prod Key 2"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    assert resp.json()["raw_secret"]
