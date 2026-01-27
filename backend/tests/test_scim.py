import os
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ["SKIP_MIGRATIONS"] = "1"

from app.main import app  # noqa: E402
import app.core.db as db_module  # noqa: E402
from app.core.scim import hash_scim_token  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402
from app.crud.users import create_user  # noqa: E402
from app.crud.tenants import create_tenant  # noqa: E402
from app.crud.memberships import create_membership  # noqa: E402
from app.crud.subscriptions import set_tenant_plan  # noqa: E402
from app.models.enums import RoleEnum, MembershipStatusEnum  # noqa: E402
from app.models.scim_mappings import SCIMExternalUserMap  # noqa: E402
from app.models.tenant_scim import TenantSCIMConfig  # noqa: E402
from app.models.plans import Plan  # noqa: E402
from app.models.users import User  # noqa: E402
from app.models.memberships import Membership  # noqa: E402
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


def _seed_scim_config(db, tenant_id: int, token: str, *, enabled: bool = True, default_role: str = "viewer"):
    plan = Plan(
        name="Enterprise",
        price_monthly=None,
        limits_json={"websites": None},
        features_json={"scim": True},
        is_active=True,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    set_tenant_plan(db, tenant_id, plan.id)
    config = TenantSCIMConfig(
        tenant_id=tenant_id,
        is_enabled=enabled,
        scim_token_hash=hash_scim_token(token),
        default_role=default_role,
    )
    db.add(config)
    db.commit()
    return config


def test_scim_requires_token_auth():
    db_url = f"sqlite:///./scim_auth_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        tenant = create_tenant(db, name="SCIM Auth")
        _seed_scim_config(db, tenant.id, "scim_secret")

    resp = client.get(
        "/scim/v2/Users",
        headers={"X-Tenant-ID": "scim-auth"},
    )
    assert resp.status_code == 401


def test_scim_provision_creates_user_and_membership():
    db_url = f"sqlite:///./scim_provision_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    token = "scim_token"
    with SessionLocal() as db:
        tenant = create_tenant(db, name="SCIM Provision")
        _seed_scim_config(db, tenant.id, token, default_role="viewer")
        owner = create_user(db, username="owner-provision@example.com", password_hash=get_password_hash("pw"))
        create_membership(db, tenant.id, owner.id, RoleEnum.OWNER)

    resp = client.post(
        "/scim/v2/Users",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "scim-provision"},
        json={"userName": "scim-user@example.com", "active": True},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["userName"] == "scim-user@example.com"

    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "scim-user@example.com").first()
        assert user is not None
        membership = (
            db.query(Membership)
            .filter(Membership.tenant_id == tenant.id, Membership.user_id == user.id)
            .first()
        )
        assert membership is not None
        assert membership.role == RoleEnum.VIEWER


def test_scim_deprovision_disables_membership_not_delete_global_user():
    db_url = f"sqlite:///./scim_deprovision_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    token = "scim_token_deprov"
    with SessionLocal() as db:
        tenant = create_tenant(db, name="SCIM Deprov")
        tenant_id = tenant.id
        _seed_scim_config(db, tenant.id, token, default_role="viewer")
        owner = create_user(db, username="owner-deprov@example.com", password_hash=get_password_hash("pw"))
        create_membership(db, tenant.id, owner.id, RoleEnum.OWNER)
        user = create_user(db, username="deprov@example.com", password_hash=get_password_hash("pw"))
        membership = create_membership(db, tenant.id, user.id, RoleEnum.VIEWER)
        mapping = SCIMExternalUserMap(tenant_id=tenant.id, scim_user_id="scim-1", user_id=user.id)
        db.add(mapping)
        db.commit()

    resp = client.delete(
        "/scim/v2/Users/scim-1",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "scim-deprov"},
    )
    assert resp.status_code == 200

    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "deprov@example.com").first()
        assert user is not None
        membership = (
            db.query(Membership)
            .filter(Membership.tenant_id == tenant_id, Membership.user_id == user.id)
            .first()
        )
        assert membership is not None
        assert membership.status == MembershipStatusEnum.SUSPENDED


def test_scim_cannot_remove_last_owner():
    db_url = f"sqlite:///./scim_owner_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    token = "scim_token_owner"
    with SessionLocal() as db:
        tenant = create_tenant(db, name="SCIM Owner")
        _seed_scim_config(db, tenant.id, token, default_role="viewer")
        owner = create_user(db, username="owner@example.com", password_hash=get_password_hash("pw"))
        create_membership(db, tenant.id, owner.id, RoleEnum.OWNER)
        mapping = SCIMExternalUserMap(tenant_id=tenant.id, scim_user_id="scim-owner", user_id=owner.id)
        db.add(mapping)
        db.commit()

    resp = client.delete(
        "/scim/v2/Users/scim-owner",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "scim-owner"},
    )
    assert resp.status_code == 409
