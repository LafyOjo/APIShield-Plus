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
from app.core.security import create_access_token, get_password_hash
from app.crud.memberships import create_membership
from app.crud.subscriptions import set_tenant_plan
from app.crud.tenant_sso import upsert_sso_config
from app.crud.tenants import create_tenant
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


def _seed_owner(SessionLocal, username: str):
    with SessionLocal() as db:
        user = create_user(db, username=username, password_hash=get_password_hash("pw"), role="user")
        plan = Plan(
            name="Enterprise",
            price_monthly=None,
            limits_json={"websites": None},
            features_json={"sso_saml": True},
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


def test_saml_metadata_endpoint_returns_valid_xml_shape():
    suffix = uuid4().hex[:8]
    SessionLocal = _setup_db(f"sqlite:///./saml_metadata_{suffix}.db")
    _username, tenant_id, tenant_slug = _seed_owner(SessionLocal, f"saml-meta-{suffix}")

    with SessionLocal() as db:
        upsert_sso_config(
            db,
            tenant_id,
            provider="saml",
            is_enabled=True,
            issuer_url=None,
            client_id=None,
            client_secret=None,
            redirect_uri=None,
            scopes=None,
            allowed_email_domains=None,
            sso_required=False,
            auto_provision=False,
            idp_entity_id="https://idp.example.com/entity",
            idp_sso_url="https://idp.example.com/sso",
            idp_x509_cert="-----BEGIN CERTIFICATE-----\nMIIFake\n-----END CERTIFICATE-----",
            sp_entity_id="https://api.example.com/saml/metadata",
            sp_acs_url="https://api.example.com/auth/saml/acs",
            sp_x509_cert=None,
        )

    resp = client.get(f"/auth/saml/metadata?tenant_id={tenant_slug}")
    assert resp.status_code == 200
    assert "application/samlmetadata+xml" in resp.headers.get("content-type", "")
    body = resp.text
    assert "EntityDescriptor" in body
    assert "AssertionConsumerService" in body
    assert "https://api.example.com/auth/saml/acs" in body


def test_saml_config_validation_requires_idp_fields():
    suffix = uuid4().hex[:8]
    SessionLocal = _setup_db(f"sqlite:///./saml_config_{suffix}.db")
    username, _tenant_id, tenant_slug = _seed_owner(SessionLocal, f"saml-config-{suffix}")
    token = create_access_token({"sub": username})

    resp = client.post(
        "/api/v1/sso/config",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
        json={
            "provider": "saml",
            "is_enabled": True,
            "sso_required": False,
            "auto_provision": False,
            "allowed_email_domains": ["example.com"],
            "sp_entity_id": "https://api.example.com/saml/metadata",
            "sp_acs_url": "https://api.example.com/auth/saml/acs",
        },
    )
    assert resp.status_code == 422
