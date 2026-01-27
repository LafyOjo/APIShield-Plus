from typing import Any, Optional

from pydantic import BaseModel

from app.models.enums import MembershipStatusEnum, RoleEnum
from app.schemas.tenant_settings import TenantSettingsRead


class MeUser(BaseModel):
    id: int
    username: str
    display_name: Optional[str] = None
    is_platform_admin: Optional[bool] = None


class MeTenant(BaseModel):
    id: int
    name: str
    slug: str


class MeMembership(BaseModel):
    tenant: MeTenant
    role: RoleEnum
    status: MembershipStatusEnum


class EntitlementsSnapshot(BaseModel):
    features: dict[str, bool]
    limits: dict[str, Any]


class MeResponse(BaseModel):
    user: MeUser
    memberships: list[MeMembership]
    active_tenant: Optional[MeTenant] = None
    active_role: Optional[RoleEnum] = None
    entitlements: Optional[EntitlementsSnapshot] = None
    settings: Optional[TenantSettingsRead] = None
