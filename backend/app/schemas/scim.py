from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel

from app.models.enums import RoleEnum


class TenantSCIMConfigUpsert(BaseModel):
    is_enabled: bool = True
    default_role: RoleEnum = RoleEnum.VIEWER
    group_role_mappings_json: Optional[dict[str, Any]] = None


class TenantSCIMConfigRead(BaseModel):
    tenant_id: int
    is_enabled: bool
    default_role: RoleEnum
    group_role_mappings_json: Optional[dict[str, Any]] = None
    token_last_rotated_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class SCIMTokenRotateResponse(BaseModel):
    scim_token: str
    token_last_rotated_at: datetime | None
