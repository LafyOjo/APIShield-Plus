import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("INVITE_TOKEN_TTL_HOURS", "1")
os.environ.setdefault("SKIP_MIGRATIONS", "1")

from app.main import app
import app.core.db as db_module
import app.core.access_log as access_log_module
import app.core.policy as policy_module
from app.core.db import Base
from app.core.tokens import verify_token
from app.core.config import settings
from app.core.security import get_password_hash
from app.crud.invites import create_invite, revoke_invite
from app.crud.memberships import create_membership
from app.crud.tenants import create_tenant
from app.crud.users import create_user
from app.models.invites import Invite
from app.models.enums import RoleEnum
from app.models.memberships import Membership


client = TestClient(app)


def _split_token(token: str) -> tuple[int, str]:
    parts = token.split("_", 2)
    assert len(parts) == 3
    _, invite_id, secret = parts
    assert invite_id.isdigit()
    assert secret
    return int(invite_id), secret


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


def test_create_invite_returns_token_once_and_hashes(monkeypatch):
    monkeypatch.setattr(settings, "INVITE_TOKEN_RETURN_IN_RESPONSE", True)
    db_url = f"sqlite:///./invite_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="owner", password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name="Acme")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=owner.id,
            role="owner",
            created_by_user_id=owner.id,
        )

    token = _login("owner")
    resp = client.post(
        "/api/v1/invites",
        json={"email": "Test@Example.com", "role": "viewer"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert "token" in payload

    with SessionLocal() as db:
        invite = db.query(Invite).filter(Invite.id == payload["id"]).first()
        assert invite is not None
        assert invite.email == "test@example.com"
        invite_id, secret = _split_token(payload["token"])
        assert invite_id == invite.id
        assert verify_token(secret, invite.token_hash)


def test_invite_requires_owner_or_admin():
    db_url = f"sqlite:///./invite_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="owner-role", password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name="RoleTenant")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=owner.id,
            role="owner",
            created_by_user_id=owner.id,
        )
        viewer = create_user(db, username="viewer-role", password_hash=get_password_hash("pw"), role="user")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=viewer.id,
            role="viewer",
            created_by_user_id=owner.id,
        )

    token = _login("viewer-role")
    resp = client.post(
        "/api/v1/invites",
        json={"email": "new@example.com", "role": "viewer"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "roletenant"},
    )
    assert resp.status_code in {403, 404}


def test_invite_fails_if_email_already_member(monkeypatch):
    monkeypatch.setattr(settings, "INVITE_TOKEN_RETURN_IN_RESPONSE", True)
    db_url = f"sqlite:///./invite_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="owner8", password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name="DupTenant")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=owner.id,
            role="owner",
            created_by_user_id=owner.id,
        )
        existing_user = create_user(db, username="member@example.com", password_hash=get_password_hash("pw"), role="user")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=existing_user.id,
            role="viewer",
            created_by_user_id=owner.id,
        )

    token = _login("owner8")
    resp = client.post(
        "/api/v1/invites",
        json={"email": "member@example.com", "role": "viewer"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "duptenant"},
    )
    assert resp.status_code == 409


def test_invite_token_returned_only_in_dev_mode(monkeypatch):
    db_url = f"sqlite:///./invite_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="owner9", password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name="TokenTenant")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=owner.id,
            role="owner",
            created_by_user_id=owner.id,
        )

    token = _login("owner9")
    monkeypatch.setattr(settings, "INVITE_TOKEN_RETURN_IN_RESPONSE", False)
    resp = client.post(
        "/api/v1/invites",
        json={"email": "devmode@example.com", "role": "viewer"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "tokentenant"},
    )
    assert resp.status_code == 200
    assert resp.json().get("token") is None

    monkeypatch.setattr(settings, "INVITE_TOKEN_RETURN_IN_RESPONSE", True)
    resp = client.post(
        "/api/v1/invites",
        json={"email": "devmode2@example.com", "role": "viewer"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "tokentenant"},
    )
    assert resp.status_code == 200
    assert resp.json().get("token")


def test_expired_token_rejected():
    db_url = f"sqlite:///./invite_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="owner2", password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name="Umbrella")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=owner.id,
            role="owner",
            created_by_user_id=owner.id,
        )
        invite, raw = create_invite(
            db,
            tenant_id=tenant.id,
            email="expired@example.com",
            role="viewer",
            created_by_user_id=owner.id,
        )
        invite.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()

        user = create_user(db, username="invitee", password_hash=get_password_hash("pw"), role="user")

    token = _login("invitee")
    resp = client.post(
        "/api/v1/invites/accept",
        json={"token": raw},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


def test_accept_invite_creates_membership_and_sets_accepted_at():
    db_url = f"sqlite:///./invite_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="owner3", password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name="Wayne")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=owner.id,
            role="owner",
            created_by_user_id=owner.id,
        )
        invite, raw = create_invite(
            db,
            tenant_id=tenant.id,
            email="new@example.com",
            role="analyst",
            created_by_user_id=owner.id,
        )
        tenant_id = tenant.id
        invite_id = invite.id
        user = create_user(db, username="newbie", password_hash=get_password_hash("pw"), role="user")
        invitee_id = user.id

    token = _login("newbie")
    resp = client.post(
        "/api/v1/invites/accept",
        json={"token": raw},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    with SessionLocal() as db:
        membership = (
            db.query(Membership)
            .filter(Membership.tenant_id == tenant_id, Membership.user_id == invitee_id)
            .first()
        )
        assert membership is not None
        assert membership.role == RoleEnum.ANALYST
        refreshed = db.query(Invite).filter(Invite.id == invite_id).first()
        assert refreshed is not None
        assert refreshed.accepted_at is not None


def test_token_replay_blocked():
    db_url = f"sqlite:///./invite_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="owner4", password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name="Oscorp")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=owner.id,
            role="owner",
            created_by_user_id=owner.id,
        )
        invite, raw = create_invite(
            db,
            tenant_id=tenant.id,
            email="replay@example.com",
            role="viewer",
            created_by_user_id=owner.id,
        )
        user = create_user(db, username="replay", password_hash=get_password_hash("pw"), role="user")

    token = _login("replay")
    first = client.post(
        "/api/v1/invites/accept",
        json={"token": raw},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first.status_code == 200
    second = client.post(
        "/api/v1/invites/accept",
        json={"token": raw},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert second.status_code == 400


def test_revoke_invite_blocks_accept():
    db_url = f"sqlite:///./invite_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="owner7", password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name="BlackMesa")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=owner.id,
            role="owner",
            created_by_user_id=owner.id,
        )
        invite, raw = create_invite(
            db,
            tenant_id=tenant.id,
            email="revoke@example.com",
            role="viewer",
            created_by_user_id=owner.id,
        )
        revoke_invite(db, tenant.id, invite.id)
        create_user(db, username="revoked", password_hash=get_password_hash("pw"), role="user")

    token = _login("revoked")
    resp = client.post(
        "/api/v1/invites/accept",
        json={"token": raw},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


def test_cross_tenant_invite_list_blocked():
    db_url = f"sqlite:///./invite_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="owner5", password_hash=get_password_hash("pw"), role="user")
        tenant_a = create_tenant(db, name="TenantA")
        create_membership(
            db,
            tenant_id=tenant_a.id,
            user_id=owner.id,
            role="owner",
            created_by_user_id=owner.id,
        )
        create_tenant(db, name="TenantB")

    token = _login("owner5")
    resp = client.get(
        "/api/v1/invites",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "tenantb"},
    )
    assert resp.status_code in {403, 404}


def test_list_invites_requires_admin_or_owner():
    db_url = f"sqlite:///./invite_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="owner-list", password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name="ListRole")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=owner.id,
            role="owner",
            created_by_user_id=owner.id,
        )
        viewer = create_user(db, username="viewer-list", password_hash=get_password_hash("pw"), role="user")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=viewer.id,
            role="viewer",
            created_by_user_id=owner.id,
        )
        create_invite(
            db,
            tenant_id=tenant.id,
            email="pending@example.com",
            role="viewer",
            created_by_user_id=owner.id,
        )

    token = _login("viewer-list")
    resp = client.get(
        "/api/v1/invites",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "listrole"},
    )
    assert resp.status_code in {403, 404}


def test_list_invites_returns_only_tenant_invites():
    db_url = f"sqlite:///./invite_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="owner-list-tenant", password_hash=get_password_hash("pw"), role="user")
        tenant_a = create_tenant(db, name="ListA")
        create_membership(
            db,
            tenant_id=tenant_a.id,
            user_id=owner.id,
            role="owner",
            created_by_user_id=owner.id,
        )
        tenant_b = create_tenant(db, name="ListB")
        invite_a, _ = create_invite(
            db,
            tenant_id=tenant_a.id,
            email="a@example.com",
            role="viewer",
            created_by_user_id=owner.id,
        )
        create_invite(
            db,
            tenant_id=tenant_b.id,
            email="b@example.com",
            role="viewer",
            created_by_user_id=owner.id,
        )
        invite_a_id = invite_a.id

    token = _login("owner-list-tenant")
    resp = client.get(
        "/api/v1/invites",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "lista"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload) == 1
    assert payload[0]["id"] == invite_a_id


def test_list_invites_excludes_accepted_by_default():
    db_url = f"sqlite:///./invite_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="owner-list-accepted", password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name="ListAccepted")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=owner.id,
            role="owner",
            created_by_user_id=owner.id,
        )
        pending_invite, _ = create_invite(
            db,
            tenant_id=tenant.id,
            email="pending@example.com",
            role="viewer",
            created_by_user_id=owner.id,
        )
        accepted_invite, _ = create_invite(
            db,
            tenant_id=tenant.id,
            email="accepted@example.com",
            role="viewer",
            created_by_user_id=owner.id,
        )
        accepted_invite.accepted_at = datetime.utcnow()
        db.commit()
        pending_id = pending_invite.id

    token = _login("owner-list-accepted")
    resp = client.get(
        "/api/v1/invites",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "listaccepted"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload) == 1
    assert payload[0]["id"] == pending_id


def test_invite_role_validation():
    db_url = f"sqlite:///./invite_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="owner6", password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name="Oscorp")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=owner.id,
            role="owner",
            created_by_user_id=owner.id,
        )

    token = _login("owner6")
    resp = client.post(
        "/api/v1/invites",
        json={"email": "bad@example.com", "role": "invalid"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "oscorp"},
    )
    assert resp.status_code == 422
