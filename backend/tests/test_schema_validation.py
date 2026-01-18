import pytest
from pydantic import ValidationError

from app.models.enums import RoleEnum
from app.schemas.invites import InviteCreate
from app.schemas.memberships import MembershipUpdate
from app.schemas.tenants import TenantCreate
from app.schemas.websites import WebsiteCreate


def test_tenant_create_rejects_invalid_slug():
    with pytest.raises(ValidationError):
        TenantCreate(name="Acme", slug="Bad_Slug")
    with pytest.raises(ValidationError):
        TenantCreate(name="Acme", slug="-bad")
    with pytest.raises(ValidationError):
        TenantCreate(name="Acme", slug="ab")


def test_website_create_rejects_domain_with_path_or_protocol():
    with pytest.raises(ValidationError):
        WebsiteCreate(domain="https://example.com")
    with pytest.raises(ValidationError):
        WebsiteCreate(domain="example.com/path")


def test_invite_create_lowercases_email():
    payload = InviteCreate(email="Test@Example.com", role=RoleEnum.VIEWER)
    assert payload.email == "test@example.com"


def test_membership_update_rejects_invalid_role():
    with pytest.raises(ValidationError):
        MembershipUpdate(role="not-a-role")
