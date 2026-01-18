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
from app.crud.users import create_user
from app.models.enums import RoleEnum
from app.models.memberships import Membership
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


def test_owner_can_change_role():
    db_url = f"sqlite:///./members_manage_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        _seed_free_plan(db)
        owner = create_user(db, username="owner-edit", password_hash=get_password_hash("pw"))
        tenant, _owner_membership = create_tenant_with_owner(
            db,
            name="ManageTenant",
            slug=None,
            owner_user=owner,
        )
        member = create_user(db, username="member-edit", password_hash=get_password_hash("pw"))
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=member.id,
            role=RoleEnum.VIEWER,
            created_by_user_id=owner.id,
        )
        db.commit()
        tenant_slug = tenant.slug
        membership_id = (
            db.query(Membership)
            .filter(Membership.tenant_id == tenant.id, Membership.user_id == member.id)
            .first()
            .id
        )

    token = _login("owner-edit")
    resp = client.patch(
        f"/api/v1/members/{membership_id}",
        json={"role": "analyst"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "analyst"


def test_admin_cannot_make_owner_if_policy_disallows():
    db_url = f"sqlite:///./members_manage_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        _seed_free_plan(db)
        owner = create_user(db, username="owner-promote", password_hash=get_password_hash("pw"))
        tenant, _owner_membership = create_tenant_with_owner(
            db,
            name="PromoteTenant",
            slug=None,
            owner_user=owner,
        )
        admin = create_user(db, username="admin-promote", password_hash=get_password_hash("pw"))
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=admin.id,
            role=RoleEnum.ADMIN,
            created_by_user_id=owner.id,
        )
        viewer = create_user(db, username="viewer-promote", password_hash=get_password_hash("pw"))
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=viewer.id,
            role=RoleEnum.VIEWER,
            created_by_user_id=owner.id,
        )
        db.commit()
        tenant_slug = tenant.slug
        membership_id = (
            db.query(Membership)
            .filter(Membership.tenant_id == tenant.id, Membership.user_id == viewer.id)
            .first()
            .id
        )

    token = _login("admin-promote")
    resp = client.patch(
        f"/api/v1/members/{membership_id}",
        json={"role": "owner"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 403


def test_member_cannot_change_roles_without_permission():
    db_url = f"sqlite:///./members_manage_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        _seed_free_plan(db)
        owner = create_user(db, username="owner-block", password_hash=get_password_hash("pw"))
        tenant, _owner_membership = create_tenant_with_owner(
            db,
            name="BlockTenant",
            slug=None,
            owner_user=owner,
        )
        viewer = create_user(db, username="viewer-block", password_hash=get_password_hash("pw"))
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=viewer.id,
            role=RoleEnum.VIEWER,
            created_by_user_id=owner.id,
        )
        db.commit()
        tenant_slug = tenant.slug
        owner_membership_id = (
            db.query(Membership)
            .filter(Membership.tenant_id == tenant.id, Membership.user_id == owner.id)
            .first()
            .id
        )

    token = _login("viewer-block")
    resp = client.patch(
        f"/api/v1/members/{owner_membership_id}",
        json={"role": "admin"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    expected = 404 if settings.TENANT_STRICT_404 else 403
    assert resp.status_code == expected


def test_remove_member_blocks_last_owner():
    db_url = f"sqlite:///./members_manage_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        _seed_free_plan(db)
        owner = create_user(db, username="owner-remove", password_hash=get_password_hash("pw"))
        tenant, _owner_membership = create_tenant_with_owner(
            db,
            name="RemoveTenant",
            slug=None,
            owner_user=owner,
        )
        db.commit()
        tenant_slug = tenant.slug
        owner_membership_id = (
            db.query(Membership)
            .filter(Membership.tenant_id == tenant.id, Membership.user_id == owner.id)
            .first()
            .id
        )

    token = _login("owner-remove")
    resp = client.delete(
        f"/api/v1/members/{owner_membership_id}",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 409


def test_remove_member_cross_tenant_returns_404():
    db_url = f"sqlite:///./members_manage_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        _seed_free_plan(db)
        owner = create_user(db, username="owner-cross", password_hash=get_password_hash("pw"))
        tenant_a, _owner_membership = create_tenant_with_owner(
            db,
            name="CrossTenantA",
            slug=None,
            owner_user=owner,
        )
        tenant_b, _ = create_tenant_with_owner(
            db,
            name="CrossTenantB",
            slug=None,
            owner_user=create_user(db, username="other-owner", password_hash=get_password_hash("pw")),
        )
        member_b = create_user(db, username="member-b", password_hash=get_password_hash("pw"))
        create_membership(
            db,
            tenant_id=tenant_b.id,
            user_id=member_b.id,
            role=RoleEnum.VIEWER,
            created_by_user_id=owner.id,
        )
        db.commit()
        tenant_a_slug = tenant_a.slug
        membership_id = (
            db.query(Membership)
            .filter(Membership.tenant_id == tenant_b.id, Membership.user_id == member_b.id)
            .first()
            .id
        )

    token = _login("owner-cross")
    resp = client.delete(
        f"/api/v1/members/{membership_id}",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_a_slug},
    )
    assert resp.status_code == 404
