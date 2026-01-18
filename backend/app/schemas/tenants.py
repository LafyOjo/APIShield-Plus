from datetime import datetime
import re
from typing import Any, Optional

from pydantic import BaseModel, constr, validator

from app.models.enums import RoleEnum
from app.schemas.memberships import MembershipRead
from app.schemas.tenant_settings import TenantSettingsRead

NameStr = constr(min_length=2, max_length=80, strip_whitespace=True)
_SLUG_RE = re.compile(r"^[a-z0-9-]{3,50}$")


class TenantRead(BaseModel):
    id: int
    name: str
    slug: str
    created_at: datetime

    class Config:
        orm_mode = True


class TenantAdminRead(TenantRead):
    deleted_at: Optional[datetime] = None


class TenantSummary(BaseModel):
    id: int
    name: str
    slug: str
    created_at: datetime
    active_plan_name: Optional[str] = None
    member_count: Optional[int] = None

    class Config:
        orm_mode = True


class TenantCreate(BaseModel):
    name: NameStr
    slug: Optional[str] = None

    @validator("slug")
    def validate_slug(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = value.strip().lower()
        if not _SLUG_RE.fullmatch(normalized) or normalized.startswith("-") or normalized.endswith("-"):
            raise ValueError("slug must be 3-50 chars, lowercase letters/numbers/hyphens, no leading/trailing hyphen")
        return normalized


class TenantUpdate(BaseModel):
    name: Optional[NameStr] = None


class TenantCreateResponse(BaseModel):
    tenant: TenantRead
    membership: MembershipRead

    class Config:
        orm_mode = True


class TenantListItem(BaseModel):
    id: int
    name: str
    slug: str
    role: RoleEnum

    class Config:
        orm_mode = True


class TenantEntitlementsSnapshot(BaseModel):
    features: dict[str, bool]
    limits: dict[str, Any]


class TenantContextResponse(BaseModel):
    tenant: TenantRead
    role: RoleEnum
    entitlements: TenantEntitlementsSnapshot
    settings: TenantSettingsRead
    plan_name: Optional[str] = None

    class Config:
        orm_mode = True
