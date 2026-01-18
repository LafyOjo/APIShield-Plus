import os
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("SKIP_MIGRATIONS", "1")

from app.main import app
import app.core.db as db_module
import app.core.access_log as access_log_module
import app.core.policy as policy_module
from app.core.config import settings
from app.core.db import Base
from app.core.security import get_password_hash
from app.crud.memberships import create_membership
from app.crud.tenants import create_tenant_with_owner
from app.crud.user_profiles import update_profile
from app.crud.users import create_user
from app.models.enums import RoleEnum
from app.models.plans import Plan


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


def _seed_free_plan(db):
    plan = Plan(
        name="Free",
        price_monthly=0,
        limits_json={"websites": 1},
        features_json={"heatmaps": False},
        is_active=True,
    )
    db.add(plan)
    db.commit()


def _login(username: str) -> str:
    resp = client.post("/login", json={"username": username, "password": "pw"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_list_members_returns_only_active_tenant_members():
    db_url = f"sqlite:///./members_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        _seed_free_plan(db)
        owner = create_user(db, username="owner", password_hash=get_password_hash("pw"))
        tenant_a, _ = create_tenant_with_owner(
            db,
            name="Tenant A",
            slug=None,
            owner_user=owner,
        )
        viewer = create_user(db, username="viewer", password_hash=get_password_hash("pw"))
        create_membership(
            db,
            tenant_id=tenant_a.id,
            user_id=viewer.id,
            role=RoleEnum.VIEWER,
            created_by_user_id=owner.id,
        )
        owner_b = create_user(db, username="ownerb", password_hash=get_password_hash("pw"))
        tenant_b, _ = create_tenant_with_owner(
            db,
            name="Tenant B",
            slug=None,
            owner_user=owner_b,
        )
        db.commit()
        tenant_a_slug = tenant_a.slug
        tenant_b_owner_id = owner_b.id

    token = _login("owner")
    resp = client.get(
        "/api/v1/members",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_a_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    user_ids = {item["user"]["id"] for item in payload}
    assert tenant_b_owner_id not in user_ids
    assert len(payload) == 2


def test_list_members_blocks_non_member():
    db_url = f"sqlite:///./members_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        _seed_free_plan(db)
        owner = create_user(db, username="owner2", password_hash=get_password_hash("pw"))
        tenant, _ = create_tenant_with_owner(
            db,
            name="Tenant C",
            slug=None,
            owner_user=owner,
        )
        outsider = create_user(db, username="outsider", password_hash=get_password_hash("pw"))
        db.commit()
        tenant_slug = tenant.slug

    token = _login("outsider")
    resp = client.get(
        "/api/v1/members",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    expected = 404 if settings.TENANT_STRICT_404 else 403
    assert resp.status_code == expected


def test_list_members_masks_email_for_viewer_if_policy_enabled():
    db_url = f"sqlite:///./members_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        _seed_free_plan(db)
        owner = create_user(db, username="owner3", password_hash=get_password_hash("pw"))
        tenant, _ = create_tenant_with_owner(
            db,
            name="Tenant D",
            slug=None,
            owner_user=owner,
        )
        viewer = create_user(db, username="viewer3", password_hash=get_password_hash("pw"))
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=viewer.id,
            role=RoleEnum.VIEWER,
            created_by_user_id=owner.id,
        )
        update_profile(db, viewer.id, {"display_name": "Viewer User", "avatar_url": "https://img.test/a.png"})
        db.commit()
        tenant_slug = tenant.slug

    token = _login("viewer3")
    resp = client.get(
        "/api/v1/members",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload
    assert all(item["user"]["email"] is None for item in payload)
    viewer_entry = next(item for item in payload if item["user"]["display_name"] == "Viewer User")
    assert viewer_entry["user"]["avatar_url"] == "https://img.test/a.png"
