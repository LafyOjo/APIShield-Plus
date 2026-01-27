import os
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("SKIP_MIGRATIONS", "1")

from app.main import app  # noqa: E402
import app.core.db as db_module  # noqa: E402
from app.core.db import Base  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402
from app.crud.users import create_user  # noqa: E402
from app.crud.tenants import create_tenant  # noqa: E402
from app.models.audit_logs import AuditLog  # noqa: E402


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


def test_status_admin_routes_require_platform_admin():
    db_url = f"sqlite:///./status_admin_block_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        create_user(db, username="user", password_hash=get_password_hash("pw"), role="user")

    token = _login("user")
    resp = client.get(
        "/api/v1/admin/status/components",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_publish_incident_logged_in_audit():
    db_url = f"sqlite:///./status_admin_audit_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        create_user(
            db,
            username="admin",
            password_hash=get_password_hash("pw"),
            role="user",
            is_platform_admin=True,
        )
        tenant = create_tenant(db, name="Status Audit Tenant")
        tenant_id = tenant.id

    token = _login("admin")
    resp = client.post(
        "/api/v1/admin/status/incidents",
        json={
            "title": "Partial outage",
            "impact_level": "major",
            "status": "investigating",
            "components_affected": ["api"],
            "message": "Investigating elevated errors.",
            "is_published": False,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    incident_id = resp.json()["id"]

    resp = client.post(
        f"/api/v1/admin/status/incidents/{incident_id}/publish",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    with SessionLocal() as db:
        audit = (
            db.query(AuditLog)
            .filter(
                AuditLog.tenant_id == tenant_id,
                AuditLog.event == "status.incident.publish",
            )
            .first()
        )
        assert audit is not None
