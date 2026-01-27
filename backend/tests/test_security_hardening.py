import os
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("ZERO_TRUST_API_KEY", "")
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
from app.models.enums import RoleEnum
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))
from security_utils import assert_endpoint_requires_role


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


def _seed_user(SessionLocal, *, username: str, tenant_name: str, role: RoleEnum):
    with SessionLocal() as db:
        user = create_user(db, username=username, password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name=tenant_name)
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=user.id,
            role=role,
            created_by_user_id=user.id,
        )
        db.commit()
        return tenant.slug, tenant.id


def _login(username: str, tenant_slug: str) -> str:
    resp = client.post(
        "/login",
        json={"username": username, "password": "pw"},
        headers={"X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_sensitive_fields_not_in_serializers():
    db_url = f"sqlite:///./security_sensitive_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_slug, _tenant_id = _seed_user(
        SessionLocal,
        username="sensitive-user",
        tenant_name="SensitiveTenant",
        role=RoleEnum.OWNER,
    )
    token = _login("sensitive-user", tenant_slug)

    resp = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    payload = resp.json()
    assert "password_hash" not in payload

    resp = client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert "password_hash" not in payload.get("user", {})


def test_cross_tenant_access_returns_404_or_403_everywhere():
    db_url = f"sqlite:///./security_cross_tenant_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_a_slug, tenant_a_id = _seed_user(
        SessionLocal,
        username="alice-sec",
        tenant_name="TenantA",
        role=RoleEnum.OWNER,
    )
    tenant_b_slug, tenant_b_id = _seed_user(
        SessionLocal,
        username="bob-sec",
        tenant_name="TenantB",
        role=RoleEnum.OWNER,
    )
    with SessionLocal() as db:
        website = create_website(db, tenant_b_id, "example-b.com", created_by_user_id=None)
        db.commit()
        website_id = website.id

    token = _login("alice-sec", tenant_a_slug)
    resp = client.get(
        f"/api/v1/websites/{website_id}",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_a_slug},
    )
    assert resp.status_code in {403, 404}


def test_role_bypass_blocked_for_admin_endpoints():
    db_url = f"sqlite:///./security_roles_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        tenant = create_tenant(db, name="RoleTenant")
        owner = create_user(db, username="owner-sec", password_hash=get_password_hash("pw"), role="user")
        viewer = create_user(db, username="viewer-sec", password_hash=get_password_hash("pw"), role="user")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=owner.id,
            role=RoleEnum.OWNER,
            created_by_user_id=owner.id,
        )
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=viewer.id,
            role=RoleEnum.VIEWER,
            created_by_user_id=owner.id,
        )
        db.commit()
        tenant_slug = tenant.slug

    owner_token = _login("owner-sec", tenant_slug)
    viewer_token = _login("viewer-sec", tenant_slug)

    assert_endpoint_requires_role(
        client,
        "POST",
        "/api/v1/invites",
        allowed_token=owner_token,
        denied_token=viewer_token,
        tenant_header=tenant_slug,
        json_body={"email": "new-user@example.com", "role": "viewer"},
        expected_allowed={200, 201},
    )
