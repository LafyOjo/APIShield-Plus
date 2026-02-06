from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field


class ResellerTenantCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    slug: Optional[str] = None
    owner_email: Optional[EmailStr] = None
    plan_key: Optional[str] = None


class ResellerTenantRead(BaseModel):
    tenant_id: int
    tenant_name: str
    tenant_slug: str
    status: str
    plan_name: Optional[str]
    subscription_status: Optional[str]
    activation_score: Optional[int]
    last_event_at: Optional[datetime]
    ingest_24h: int
    billing_mode: str


class ResellerTenantProvisioned(BaseModel):
    tenant: ResellerTenantRead
    invite_email: Optional[str] = None
    invite_token: Optional[str] = None


class ResellerManagedTenantRead(ResellerTenantRead):
    created_at: datetime


class ResellerAccountRead(BaseModel):
    billing_mode: str
    allowed_plans: Optional[list[str]] = None
    is_enabled: bool


class ResellerManagedTenantList(BaseModel):
    account: ResellerAccountRead
    tenants: list[ResellerManagedTenantRead]
