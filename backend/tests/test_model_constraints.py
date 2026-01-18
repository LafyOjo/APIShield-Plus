import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "secret")

import app.models  # noqa: F401
from app.core.db import Base
from app.crud.invites import create_invite
from app.models.api_keys import APIKey
from app.models.data_retention import DataRetentionPolicy
from app.models.enums import MembershipStatusEnum, RoleEnum, WebsiteStatusEnum
from app.models.feature_entitlements import FeatureEntitlement
from app.models.invites import Invite
from app.models.memberships import Membership
from app.models.tenant_settings import TenantSettings
from app.models.tenant_usage import TenantUsage
from app.models.tenants import Tenant
from app.models.website_environments import WebsiteEnvironment
from app.models.websites import Website
from tests.factories import (
    make_tenant,
    make_user,
    make_website,
)


@pytest.fixture
def db_session(tmp_path):
    db_url = f"sqlite:///{tmp_path}/constraints_test.db"
    os.environ["DATABASE_URL"] = db_url
    os.environ["SKIP_MIGRATIONS"] = "1"
    engine = create_engine(db_url, future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    with TestingSessionLocal() as session:
        yield session


def test_tenant_slug_unique_constraint(db_session):
    tenant = Tenant(name="Acme", slug="duplicate")
    db_session.add(tenant)
    db_session.commit()

    duplicate = Tenant(name="Other", slug="duplicate")
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_tenant_name_required(db_session):
    tenant = Tenant(name=None, slug="missing-name")
    db_session.add(tenant)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_membership_unique_tenant_user_constraint(db_session):
    tenant = make_tenant(db_session, name="Acme")
    user = make_user(db_session, username="alice")
    membership = Membership(
        tenant_id=tenant.id,
        user_id=user.id,
        role=RoleEnum.OWNER,
        status=MembershipStatusEnum.ACTIVE,
    )
    db_session.add(membership)
    db_session.commit()

    duplicate = Membership(
        tenant_id=tenant.id,
        user_id=user.id,
        role=RoleEnum.OWNER,
        status=MembershipStatusEnum.ACTIVE,
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_membership_role_enum_validity(db_session):
    tenant = make_tenant(db_session, name="Umbrella")
    user = make_user(db_session, username="bob")
    membership = Membership(
        tenant_id=tenant.id,
        user_id=user.id,
        role="invalid-role",
        status=MembershipStatusEnum.ACTIVE,
    )
    db_session.add(membership)
    with pytest.raises((ValueError, StatementError, IntegrityError)):
        db_session.commit()
    db_session.rollback()


def test_invite_required_fields(db_session):
    tenant = make_tenant(db_session, name="Wayne")
    invite = Invite(
        tenant_id=tenant.id,
        email="test@example.com",
        role=RoleEnum.VIEWER,
        token_hash=None,
        expires_at=datetime.now(timezone.utc),
    )
    db_session.add(invite)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    invite = Invite(
        tenant_id=tenant.id,
        email="test@example.com",
        role=RoleEnum.VIEWER,
        token_hash="hash",
        expires_at=None,
    )
    db_session.add(invite)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_invite_email_normalized(db_session):
    tenant = make_tenant(db_session, name="Stark")
    user = make_user(db_session, username="tony")
    invite, _token = create_invite(
        db_session,
        tenant_id=tenant.id,
        email="Test@Example.com",
        role=RoleEnum.ANALYST,
        created_by_user_id=user.id,
    )
    assert invite.email == "test@example.com"


def test_website_domain_normalization(db_session):
    tenant = make_tenant(db_session, name="Oscorp")
    website = make_website(db_session, tenant=tenant, domain="https://Example.com/")
    assert website.domain == "example.com"


def test_website_domain_unique_per_tenant(db_session):
    tenant = make_tenant(db_session, name="Daily Bugle")
    website = Website(
        tenant_id=tenant.id,
        domain="example.com",
        status=WebsiteStatusEnum.ACTIVE,
    )
    db_session.add(website)
    db_session.commit()

    duplicate = Website(
        tenant_id=tenant.id,
        domain="example.com",
        status=WebsiteStatusEnum.ACTIVE,
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_environment_unique_per_website(db_session):
    tenant = make_tenant(db_session, name="Initech")
    website = make_website(db_session, tenant=tenant, domain="initech.com")
    duplicate = WebsiteEnvironment(website_id=website.id, name="production")
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_api_key_public_key_unique(db_session):
    tenant = make_tenant(db_session, name="Hooli")
    website = make_website(db_session, tenant=tenant, domain="hooli.com")
    environment = website.environments[0]
    key = APIKey(
        tenant_id=tenant.id,
        website_id=website.id,
        environment_id=environment.id,
        public_key="pk_duplicate",
        secret_hash="hash",
        status="active",
    )
    db_session.add(key)
    db_session.commit()

    duplicate = APIKey(
        tenant_id=tenant.id,
        website_id=website.id,
        environment_id=environment.id,
        public_key="pk_duplicate",
        secret_hash="hash",
        status="active",
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_api_key_requires_secret_hash(db_session):
    tenant = make_tenant(db_session, name="Pied Piper")
    website = make_website(db_session, tenant=tenant, domain="piedpiper.com")
    environment = website.environments[0]
    key = APIKey(
        tenant_id=tenant.id,
        website_id=website.id,
        environment_id=environment.id,
        public_key="pk_missing_hash",
        secret_hash=None,
        status="active",
    )
    db_session.add(key)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_api_key_revoked_at_persists(db_session):
    tenant = make_tenant(db_session, name="Globex")
    website = make_website(db_session, tenant=tenant, domain="globex.com")
    environment = website.environments[0]
    key = APIKey(
        tenant_id=tenant.id,
        website_id=website.id,
        environment_id=environment.id,
        public_key="pk_revoked",
        secret_hash="hash",
        status="revoked",
        revoked_at=datetime.now(timezone.utc),
    )
    db_session.add(key)
    db_session.commit()
    db_session.refresh(key)
    assert key.revoked_at is not None


def test_tenant_settings_unique_tenant(db_session):
    tenant = Tenant(name="Soylent", slug="soylent")
    db_session.add(tenant)
    db_session.commit()
    settings = TenantSettings(
        tenant_id=tenant.id,
        timezone="UTC",
        retention_days=30,
        event_retention_days=30,
        ip_raw_retention_days=7,
        alert_prefs={},
    )
    db_session.add(settings)
    db_session.commit()

    duplicate = TenantSettings(
        tenant_id=tenant.id,
        timezone="UTC",
        retention_days=30,
        event_retention_days=30,
        ip_raw_retention_days=7,
        alert_prefs={},
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_usage_unique_tenant_period(db_session):
    tenant = make_tenant(db_session, name="Vandelay")
    period_start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    usage = TenantUsage(
        tenant_id=tenant.id,
        period_start=period_start,
    )
    db_session.add(usage)
    db_session.commit()

    duplicate = TenantUsage(
        tenant_id=tenant.id,
        period_start=period_start,
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_retention_unique_tenant_event(db_session):
    tenant = Tenant(name="Aperture", slug="aperture")
    db_session.add(tenant)
    db_session.commit()
    policy = DataRetentionPolicy(
        tenant_id=tenant.id,
        event_type="alert",
        days=30,
    )
    db_session.add(policy)
    db_session.commit()

    duplicate = DataRetentionPolicy(
        tenant_id=tenant.id,
        event_type="alert",
        days=60,
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_entitlements_unique_tenant_feature(db_session):
    tenant = Tenant(name="Black Mesa", slug="black-mesa")
    db_session.add(tenant)
    db_session.commit()
    entitlement = FeatureEntitlement(
        tenant_id=tenant.id,
        feature="custom_feature",
        enabled=True,
        source="plan",
    )
    db_session.add(entitlement)
    db_session.commit()

    duplicate = FeatureEntitlement(
        tenant_id=tenant.id,
        feature="custom_feature",
        enabled=False,
        source="plan",
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
