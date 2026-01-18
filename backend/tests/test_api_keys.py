import os
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("API_KEY_SECRET_RETURN_IN_RESPONSE", "true")
os.environ["SKIP_MIGRATIONS"] = "1"

from app.main import app
import app.core.db as db_module
import app.core.access_log as access_log_module
import app.core.policy as policy_module
from app.core.config import settings
from app.core.db import Base
from app.core.keys import hash_secret, verify_secret
from app.core.security import get_password_hash
from app.crud.api_keys import create_api_key
from app.crud.tenants import create_tenant
from app.crud.website_environments import list_environments
from app.crud.websites import create_website
from app.crud.users import create_user
from app.crud.memberships import create_membership
from app.models.api_keys import APIKey
from app.crud import api_keys as api_keys_crud


client = TestClient(app)
settings.API_KEY_SECRET_RETURN_IN_RESPONSE = True


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


def _create_user_with_role(SessionLocal, username: str, role: str) -> int:
    with SessionLocal() as db:
        user = create_user(db, username=username, password_hash=get_password_hash("pw"), role=role)
        return user.id


def _add_membership(SessionLocal, user_id: int, tenant_id: int, role: str) -> None:
    with SessionLocal() as db:
        create_membership(
            db,
            tenant_id=tenant_id,
            user_id=user_id,
            role=role,
            created_by_user_id=user_id,
        )


def _login(username: str) -> str:
    resp = client.post("/login", json={"username": username, "password": "pw"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _setup_tenant_website_env(SessionLocal, prefix: str):
    with SessionLocal() as db:
        tenant = create_tenant(db, name=f"{prefix}-tenant")
        website = create_website(db, tenant.id, f"{prefix}.example.com")
        environments = list_environments(db, website.id)
        environment = next(env for env in environments if env.name == "production")
        db.refresh(tenant)
        db.refresh(website)
        return tenant, website, environment


def test_create_api_key_returns_secret_once_and_persists_hash():
    suffix = uuid4().hex[:8]
    SessionLocal = _setup_db(f"sqlite:///./api_keys_{suffix}.db")
    username = f"owner_{suffix}"
    user_id = _create_user_with_role(SessionLocal, username, "owner")
    tenant, website, environment = _setup_tenant_website_env(SessionLocal, f"acme-{suffix}")
    _add_membership(SessionLocal, user_id=user_id, tenant_id=tenant.id, role="owner")
    token = _login(username)

    resp = client.post(
        f"/api/v1/websites/{website.id}/environments/{environment.id}/keys",
        json={"name": "Prod Key", "environment_id": environment.id},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant.slug},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert "raw_secret" in payload
    assert "public_key" in payload

    raw_secret = payload["raw_secret"]
    public_key = payload["public_key"]
    with SessionLocal() as db:
        api_key = db.query(APIKey).filter(APIKey.public_key == public_key).first()
        assert api_key is not None
        assert api_key.secret_hash != raw_secret
        assert verify_secret(raw_secret, api_key.secret_hash)
        assert api_key.created_by_user_id == user_id


def test_list_api_keys_never_returns_secret_or_hash():
    suffix = uuid4().hex[:8]
    SessionLocal = _setup_db(f"sqlite:///./api_keys_{suffix}.db")
    username = f"owner_list_{suffix}"
    user_id = _create_user_with_role(SessionLocal, username, "owner")
    tenant, website, environment = _setup_tenant_website_env(SessionLocal, f"list-{suffix}")
    _add_membership(SessionLocal, user_id=user_id, tenant_id=tenant.id, role="owner")
    token = _login(username)

    with SessionLocal() as db:
        create_api_key(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            environment_id=environment.id,
            name="List Key",
            created_by_user_id=None,
        )

    resp = client.get(
        f"/api/v1/websites/{website.id}/keys",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant.slug},
    )
    assert resp.status_code == 200
    items = resp.json()
    assert items
    for item in items:
        assert "raw_secret" not in item
        assert "secret_hash" not in item


def test_revoke_api_key_sets_revoked_at_and_blocks_future_rotation_without_owner():
    suffix = uuid4().hex[:8]
    SessionLocal = _setup_db(f"sqlite:///./api_keys_{suffix}.db")
    owner = f"owner_revoke_{suffix}"
    viewer = f"viewer_revoke_{suffix}"
    owner_id = _create_user_with_role(SessionLocal, owner, "owner")
    viewer_id = _create_user_with_role(SessionLocal, viewer, "viewer")
    tenant, website, environment = _setup_tenant_website_env(SessionLocal, f"revoke-{suffix}")
    _add_membership(SessionLocal, user_id=owner_id, tenant_id=tenant.id, role="owner")
    _add_membership(SessionLocal, user_id=viewer_id, tenant_id=tenant.id, role="viewer")
    owner_token = _login(owner)
    viewer_token = _login(viewer)

    with SessionLocal() as db:
        api_key, _ = create_api_key(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            environment_id=environment.id,
            name="Revoke Key",
            created_by_user_id=None,
        )

    revoke_resp = client.post(
        f"/api/v1/keys/{api_key.id}/revoke",
        headers={"Authorization": f"Bearer {owner_token}", "X-Tenant-ID": tenant.slug},
    )
    assert revoke_resp.status_code == 200
    assert revoke_resp.json()["revoked_at"] is not None

    rotate_resp = client.post(
        f"/api/v1/keys/{api_key.id}/rotate",
        headers={"Authorization": f"Bearer {viewer_token}", "X-Tenant-ID": tenant.slug},
    )
    assert rotate_resp.status_code in {403, 404}


def test_rotate_api_key_revokes_old_and_creates_new():
    suffix = uuid4().hex[:8]
    SessionLocal = _setup_db(f"sqlite:///./api_keys_{suffix}.db")
    username = f"owner_rotate_{suffix}"
    user_id = _create_user_with_role(SessionLocal, username, "owner")
    tenant, website, environment = _setup_tenant_website_env(SessionLocal, f"rotate-{suffix}")
    _add_membership(SessionLocal, user_id=user_id, tenant_id=tenant.id, role="owner")
    token = _login(username)

    with SessionLocal() as db:
        api_key, _ = create_api_key(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            environment_id=environment.id,
            name="Rotate Key",
            created_by_user_id=None,
        )

    resp = client.post(
        f"/api/v1/keys/{api_key.id}/rotate",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant.slug},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["public_key"] != api_key.public_key
    assert data["raw_secret"]

    with SessionLocal() as db:
        old = db.query(APIKey).filter(APIKey.id == api_key.id).first()
        new = db.query(APIKey).filter(APIKey.id == data["id"]).first()
        assert old is not None and old.revoked_at is not None
        assert new is not None and new.revoked_at is None


def test_cross_tenant_access_returns_404():
    suffix = uuid4().hex[:8]
    SessionLocal = _setup_db(f"sqlite:///./api_keys_{suffix}.db")
    username = f"owner_cross_{suffix}"
    user_id = _create_user_with_role(SessionLocal, username, "owner")
    tenant_a, website_a, _ = _setup_tenant_website_env(SessionLocal, f"cross-a-{suffix}")
    tenant_b, _, _ = _setup_tenant_website_env(SessionLocal, f"cross-b-{suffix}")
    _add_membership(SessionLocal, user_id=user_id, tenant_id=tenant_a.id, role="owner")
    _add_membership(SessionLocal, user_id=user_id, tenant_id=tenant_b.id, role="owner")
    token = _login(username)

    resp = client.get(
        f"/api/v1/websites/{website_a.id}/keys",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_b.slug},
    )
    assert resp.status_code == 404


def test_public_key_uniqueness_collision_handling(monkeypatch):
    suffix = uuid4().hex[:8]
    SessionLocal = _setup_db(f"sqlite:///./api_keys_{suffix}.db")
    tenant, website, environment = _setup_tenant_website_env(SessionLocal, f"collision-{suffix}")

    with SessionLocal() as db:
        existing = APIKey(
            tenant_id=tenant.id,
            website_id=website.id,
            environment_id=environment.id,
            public_key="pk_collision",
            secret_hash=hash_secret("sk_collision"),
            status="active",
        )
        db.add(existing)
        db.commit()

        keys = iter(["pk_collision", "pk_unique"])

        def fake_generate():
            return next(keys)

        monkeypatch.setattr(api_keys_crud, "generate_public_key", fake_generate)
        api_key, _ = create_api_key(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            environment_id=environment.id,
            name="Collision Key",
            created_by_user_id=None,
        )
        assert api_key.public_key == "pk_unique"
