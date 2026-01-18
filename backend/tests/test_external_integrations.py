import os
from uuid import uuid4

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("INTEGRATION_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))

from app.main import app
import app.core.db as db_module
import app.core.access_log as access_log_module
import app.core.policy as policy_module
from app.core.crypto import decrypt_json, encrypt_json
from app.core.db import Base
from app.core.security import get_password_hash
from app.crud.external_integrations import create_integration
from app.crud.memberships import create_membership
from app.crud.tenants import create_tenant
from app.crud.users import create_user
from app.models.external_integrations import ExternalIntegration


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


def test_encryption_round_trip():
    payload = {"client_id": "abc", "secret": "shh"}
    encrypted = encrypt_json(payload)
    assert encrypted != ""
    decrypted = decrypt_json(encrypted)
    assert decrypted == payload


def test_create_integration_stores_encrypted_config():
    db_url = f"sqlite:///./integrations_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        tenant = create_tenant(db, name="Acme")
        integration = create_integration(
            db,
            tenant_id=tenant.id,
            integration_type="slack",
            config={"token": "xoxb", "channel": "#alerts"},
        )
        stored = (
            db.query(ExternalIntegration)
            .filter(ExternalIntegration.id == integration.id)
            .first()
        )
        assert stored is not None
        assert stored.config_encrypted != ""
        assert decrypt_json(stored.config_encrypted)["token"] == "xoxb"


def test_non_owner_cannot_access_integrations():
    db_url = f"sqlite:///./integrations_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="owner", password_hash=get_password_hash("pw"), role="user")
        viewer = create_user(db, username="viewer", password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name="Umbrella")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=owner.id,
            role="owner",
            created_by_user_id=owner.id,
        )
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=viewer.id,
            role="viewer",
            created_by_user_id=owner.id,
        )
        tenant_slug = tenant.slug

    token = _login("viewer")
    resp = client.get(
        "/api/v1/integrations",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code in {403, 404}


def test_cross_tenant_access_blocked():
    db_url = f"sqlite:///./integrations_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="owner2", password_hash=get_password_hash("pw"), role="user")
        tenant_a = create_tenant(db, name="TenantA")
        tenant_b = create_tenant(db, name="TenantB")
        create_membership(
            db,
            tenant_id=tenant_a.id,
            user_id=owner.id,
            role="owner",
            created_by_user_id=owner.id,
        )
        create_integration(
            db,
            tenant_id=tenant_b.id,
            integration_type="slack",
            config={"token": "xoxb"},
        )
        tenant_b_slug = tenant_b.slug

    token = _login("owner2")
    resp = client.get(
        "/api/v1/integrations",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_b_slug},
    )
    assert resp.status_code in {403, 404}
