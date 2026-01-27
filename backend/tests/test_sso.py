import os
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("INTEGRATION_ENCRYPTION_KEY", "a" * 32)
os.environ.setdefault("ZERO_TRUST_API_KEY", "")
os.environ.setdefault("SKIP_MIGRATIONS", "1")
os.environ.setdefault("FRONTEND_BASE_URL", "http://testserver")

from app.main import app
import app.core.db as db_module
import app.core.access_log as access_log_module
import app.core.policy as policy_module
from app.core.db import Base
from app.core.oidc import create_state_token
from app.core.security import create_access_token, get_password_hash
from app.crud.memberships import create_membership
from app.crud.subscriptions import set_tenant_plan
from app.crud.tenant_sso import decrypt_client_secret, get_sso_config, upsert_sso_config
from app.crud.tenants import create_tenant
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


def _seed_owner(SessionLocal, username: str):
    with SessionLocal() as db:
        user = create_user(db, username=username, password_hash=get_password_hash("pw"), role="user")
        plan = Plan(
            name="Business",
            price_monthly=399,
            limits_json={"websites": 25},
            features_json={"sso_oidc": True},
            is_active=True,
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)
        tenant = create_tenant(db, name=f"{username}-tenant")
        set_tenant_plan(db, tenant.id, plan.id)
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=user.id,
            role=RoleEnum.OWNER,
            created_by_user_id=user.id,
        )
        db.commit()
        return user.username, tenant.id, tenant.slug


def test_sso_config_secrets_encrypted():
    suffix = uuid4().hex[:8]
    SessionLocal = _setup_db(f"sqlite:///./sso_config_{suffix}.db")
    username, tenant_id, tenant_slug = _seed_owner(SessionLocal, f"sso-owner-{suffix}")
    token = create_access_token({"sub": username})

    resp = client.post(
        "/api/v1/sso/config",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
        json={
            "provider": "oidc",
            "is_enabled": True,
            "issuer_url": "https://issuer.example.com",
            "client_id": "client-123",
            "client_secret": "super-secret",
            "redirect_uri": "https://api.example.com/auth/oidc/callback",
            "scopes": "openid email profile",
            "allowed_email_domains": ["example.com"],
            "sso_required": False,
            "auto_provision": False,
        },
    )
    assert resp.status_code == 200

    with SessionLocal() as db:
        config = get_sso_config(db, tenant_id)
        assert config is not None
        assert config.client_secret_enc != "super-secret"
        assert decrypt_client_secret(config.client_secret_enc) == "super-secret"


def test_sso_required_blocks_password_login():
    suffix = uuid4().hex[:8]
    SessionLocal = _setup_db(f"sqlite:///./sso_required_{suffix}.db")
    username, tenant_id, tenant_slug = _seed_owner(SessionLocal, f"sso-required-{suffix}")

    with SessionLocal() as db:
        upsert_sso_config(
            db,
            tenant_id,
            provider="oidc",
            is_enabled=True,
            issuer_url="https://issuer.example.com",
            client_id="client-123",
            client_secret="top-secret",
            redirect_uri="https://api.example.com/auth/oidc/callback",
            scopes="openid email profile",
            allowed_email_domains=["example.com"],
            sso_required=True,
            auto_provision=False,
            idp_entity_id=None,
            idp_sso_url=None,
            idp_x509_cert=None,
            sp_entity_id=None,
            sp_acs_url=None,
            sp_x509_cert=None,
        )

    resp = client.post(
        "/login",
        headers={"X-Tenant-ID": tenant_slug},
        json={"username": username, "password": "pw"},
    )
    assert resp.status_code == 403


def test_sso_domain_restriction_blocks_invalid_domain(monkeypatch):
    suffix = uuid4().hex[:8]
    SessionLocal = _setup_db(f"sqlite:///./sso_domain_{suffix}.db")
    _username, tenant_id, tenant_slug = _seed_owner(SessionLocal, f"sso-domain-{suffix}")

    with SessionLocal() as db:
        upsert_sso_config(
            db,
            tenant_id,
            provider="oidc",
            is_enabled=True,
            issuer_url="https://issuer.example.com",
            client_id="client-123",
            client_secret="top-secret",
            redirect_uri="https://api.example.com/auth/oidc/callback",
            scopes="openid email profile",
            allowed_email_domains=["example.com"],
            sso_required=False,
            auto_provision=True,
            idp_entity_id=None,
            idp_sso_url=None,
            idp_x509_cert=None,
            sp_entity_id=None,
            sp_acs_url=None,
            sp_x509_cert=None,
        )

    import app.api.oidc as oidc_api

    monkeypatch.setattr(
        oidc_api,
        "fetch_discovery",
        lambda issuer_url: {
            "issuer": issuer_url,
            "authorization_endpoint": "https://issuer.example.com/auth",
            "token_endpoint": "https://issuer.example.com/token",
            "jwks_uri": "https://issuer.example.com/jwks",
        },
    )
    monkeypatch.setattr(
        oidc_api,
        "exchange_code_for_tokens",
        lambda **kwargs: {"id_token": "dummy"},
    )
    monkeypatch.setattr(
        oidc_api,
        "verify_id_token",
        lambda **kwargs: {"email": "user@blocked.com"},
    )

    state = create_state_token(tenant_id, nonce="nonce", next_path="/sso/callback")
    resp = client.get(f"/auth/oidc/callback?code=abc&state={state}")
    assert resp.status_code == 403


def test_oidc_callback_creates_or_links_user_correctly(monkeypatch):
    suffix = uuid4().hex[:8]
    SessionLocal = _setup_db(f"sqlite:///./sso_callback_{suffix}.db")
    _username, tenant_id, tenant_slug = _seed_owner(SessionLocal, f"sso-callback-{suffix}")

    with SessionLocal() as db:
        upsert_sso_config(
            db,
            tenant_id,
            provider="oidc",
            is_enabled=True,
            issuer_url="https://issuer.example.com",
            client_id="client-123",
            client_secret="top-secret",
            redirect_uri="https://api.example.com/auth/oidc/callback",
            scopes="openid email profile",
            allowed_email_domains=["example.com"],
            sso_required=False,
            auto_provision=True,
            idp_entity_id=None,
            idp_sso_url=None,
            idp_x509_cert=None,
            sp_entity_id=None,
            sp_acs_url=None,
            sp_x509_cert=None,
        )

    import app.api.oidc as oidc_api

    monkeypatch.setattr(
        oidc_api,
        "fetch_discovery",
        lambda issuer_url: {
            "issuer": issuer_url,
            "authorization_endpoint": "https://issuer.example.com/auth",
            "token_endpoint": "https://issuer.example.com/token",
            "jwks_uri": "https://issuer.example.com/jwks",
        },
    )
    monkeypatch.setattr(
        oidc_api,
        "exchange_code_for_tokens",
        lambda **kwargs: {"id_token": "dummy"},
    )
    monkeypatch.setattr(
        oidc_api,
        "verify_id_token",
        lambda **kwargs: {"email": f"new-{suffix}@example.com"},
    )

    state = create_state_token(tenant_id, nonce="nonce", next_path="/sso/callback")
    resp = client.get(f"/auth/oidc/callback?code=abc&state={state}", follow_redirects=False)
    assert resp.status_code in {302, 307}
    assert resp.headers.get("location", "").startswith("http://testserver")

    with SessionLocal() as db:
        membership = (
            db.query(Membership)
            .filter(Membership.tenant_id == tenant_id)
            .order_by(Membership.id.desc())
            .first()
        )
        assert membership is not None
