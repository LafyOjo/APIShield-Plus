from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class PartnerMeRead(BaseModel):
    partner_id: int
    partner_name: str
    partner_code: str
    role: str
    status: str


class PartnerMetricsRead(BaseModel):
    from_ts: datetime
    to_ts: datetime
    leads: int
    signups: int
    activated: int
    conversions: int
    commission_pending: float
    commission_earned: float
    commission_paid: float
    commission_owed: float


class PartnerLeadRead(BaseModel):
    lead_id: str
    status: str
    created_at: datetime
    source_meta: Optional[dict[str, Any]] = None
    tenant_ref: Optional[str] = None


class PartnerCommissionRead(BaseModel):
    id: int
    tenant_ref: str
    plan_name: Optional[str]
    subscription_status: Optional[str]
    conversion_date: Optional[datetime]
    amount: float
    currency: str
    status: str
    earned_at: Optional[datetime]
    paid_at: Optional[datetime]
