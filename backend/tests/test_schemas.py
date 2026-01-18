import json
import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "secret")

from app.core.db import Base
from app.models.api_keys import APIKey
from app.models.enums import MembershipStatusEnum, RoleEnum, WebsiteStatusEnum
from app.models.external_integrations import ExternalIntegration
from app.models.invites import Invite
from app.models.memberships import Membership
from app.models.plans import Plan
from app.models.tenants import Tenant
from app.models.user_profiles import UserProfile
from app.models.users import User
from app.models.website_environments import WebsiteEnvironment
from app.models.websites import Website
from app.schemas.api_keys import APIKeyRead
from app.schemas.external_integrations import ExternalIntegrationRead
from app.schemas.invites import InviteRead
from app.schemas.memberships import MembershipUserRead
from app.schemas.plans import PlanRead
from app.schemas.tenants import TenantRead


@pytest.fixture
def db_session(tmp_path):
    db_url = f"sqlite:///{tmp_path}/schemas_test.db"
    os.environ["DATABASE_URL"] = db_url
    os.environ["SKIP_MIGRATIONS"] = "1"
    engine = create_engine(db_url, future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    with TestingSessionLocal() as session:
        yield session


def test_tenant_read_schema_serializes(db_session):
    tenant = Tenant(name="Acme", slug="acme")
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    payload = TenantRead.from_orm(tenant).json()
    data = json.loads(payload)
    assert data["slug"] == "acme"
    parsed = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
    assert parsed.tzinfo is not None


def test_membership_user_read_does_not_leak_sensitive_user_fields(db_session):
    tenant = Tenant(name="Umbrella", slug="umbrella")
    user = User(username="alice@example.com", password_hash="hash", role="user")
    db_session.add_all([tenant, user])
    db_session.commit()
    profile = UserProfile(user_id=user.id, display_name="Alice")
    membership = Membership(
        tenant_id=tenant.id,
        user_id=user.id,
        role=RoleEnum.OWNER,
        status=MembershipStatusEnum.ACTIVE,
    )
    db_session.add_all([profile, membership])
    db_session.commit()
    db_session.refresh(membership)
    data = MembershipUserRead.from_orm(membership).dict()
    assert data["user"]["email"] == user.username
    assert data["user"]["display_name"] == "Alice"
    assert "password_hash" not in data["user"]
    assert "role" not in data["user"]


def test_plan_read_includes_limits_and_features(db_session):
    plan = Plan(
        name="Free",
        price_monthly=None,
        limits_json={"websites": 1},
        features_json={"heatmaps": False},
        is_active=True,
    )
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    data = PlanRead.from_orm(plan).dict()
    assert data["limits_json"]["websites"] == 1
    assert data["features_json"]["heatmaps"] is False


def test_invite_read_schema_excludes_token_hash(db_session):
    tenant = Tenant(name="Stark", slug="stark")
    db_session.add(tenant)
    db_session.commit()
    invite = Invite(
        tenant_id=tenant.id,
        email="invitee@example.com",
        role=RoleEnum.VIEWER,
        token_hash="hash",
        expires_at=datetime.now(timezone.utc),
    )
    db_session.add(invite)
    db_session.commit()
    data = InviteRead.from_orm(invite).dict()
    assert "token_hash" not in data


def test_api_key_read_excludes_secret_hash(db_session):
    tenant = Tenant(name="Pied Piper", slug="pied-piper")
    db_session.add(tenant)
    db_session.commit()
    website = Website(
        tenant_id=tenant.id,
        domain="piedpiper.com",
        status=WebsiteStatusEnum.ACTIVE,
    )
    db_session.add(website)
    db_session.commit()
    db_session.refresh(website)
    environment = WebsiteEnvironment(website_id=website.id, name="production")
    db_session.add(environment)
    db_session.commit()
    api_key = APIKey(
        tenant_id=tenant.id,
        website_id=website.id,
        environment_id=environment.id,
        public_key="pk_safe",
        secret_hash="hash",
        status="active",
    )
    db_session.add(api_key)
    db_session.commit()
    data = APIKeyRead.from_orm(api_key).dict()
    assert "secret_hash" not in data


def test_external_integration_read_excludes_config(db_session):
    tenant = Tenant(name="Initech", slug="initech")
    db_session.add(tenant)
    db_session.commit()
    integration = ExternalIntegration(
        tenant_id=tenant.id,
        type="slack",
        config_encrypted="encrypted",
        status="active",
    )
    db_session.add(integration)
    db_session.commit()
    data = ExternalIntegrationRead.from_orm(integration).dict()
    assert "config" not in data
    assert "config_encrypted" not in data
