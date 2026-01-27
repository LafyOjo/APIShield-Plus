import os
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ["SKIP_MIGRATIONS"] = "1"

from app.main import app  # noqa: E402
import app.core.db as db_module  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402
from app.crud.users import create_user  # noqa: E402
from app.crud.tenants import create_tenant  # noqa: E402
from app.crud.memberships import create_membership  # noqa: E402
from app.models.audit_logs import AuditLog  # noqa: E402
from app.models.enums import RoleEnum  # noqa: E402
from app.models.api_keys import APIKey  # noqa: E402
from app.models.website_environments import WebsiteEnvironment  # noqa: E402
from app.models.websites import Website  # noqa: E402
from app.core.db import Base  # noqa: E402


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
    Base.metadata.create_all(bind=engine)
    return SessionLocal


def _login(username: str) -> str:
    resp = client.post("/login", json={"username": username, "password": "pw"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_admin_routes_require_platform_admin():
    db_url = f"sqlite:///./admin_block_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        create_user(db, username="user", password_hash=get_password_hash("pw"), role="user")

    token = _login("user")
    resp = client.get("/api/v1/admin/tenants", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_support_view_as_requires_reason_and_is_audited():
    db_url = f"sqlite:///./admin_support_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        admin = create_user(
            db,
            username="admin",
            password_hash=get_password_hash("pw"),
            role="user",
            is_platform_admin=True,
        )
        tenant = create_tenant(db, name="Support Tenant")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=admin.id,
            role=RoleEnum.OWNER,
            created_by_user_id=admin.id,
        )

    token = _login("admin")
    resp = client.post(
        "/api/v1/admin/support/view-as",
        json={"tenant_id": tenant.id, "reason": "investigate ingestion errors"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["support_token"]
    assert payload["tenant_id"] == tenant.id

    with SessionLocal() as db:
        audit = (
            db.query(AuditLog)
            .filter(
                AuditLog.tenant_id == tenant.id,
                AuditLog.event.like("admin.support_view_as:%"),
            )
            .first()
        )
        assert audit is not None


def test_admin_console_does_not_expose_secret_keys():
    db_url = f"sqlite:///./admin_secret_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    now = datetime.utcnow()
    with SessionLocal() as db:
        admin = create_user(
            db,
            username="admin",
            password_hash=get_password_hash("pw"),
            role="user",
            is_platform_admin=True,
        )
        tenant = create_tenant(db, name="Secret Tenant")
        tenant_id = tenant.id
        create_membership(
            db,
            tenant_id=tenant_id,
            user_id=admin.id,
            role=RoleEnum.OWNER,
            created_by_user_id=admin.id,
        )
        website = Website(tenant_id=tenant_id, domain="secret.example.com")
        db.add(website)
        db.commit()
        db.refresh(website)
        env = WebsiteEnvironment(website_id=website.id, name="production")
        db.add(env)
        db.commit()
        db.refresh(env)
        db.add(
            APIKey(
                tenant_id=tenant_id,
                website_id=website.id,
                environment_id=env.id,
                public_key="pk_public",
                secret_hash="hash",
                created_at=now,
            )
        )
        db.commit()

    token = _login("admin")
    resp = client.get(
        f"/api/v1/admin/tenants/{tenant_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.text
    assert "secret_hash" not in body
    assert "pk_public" not in body
