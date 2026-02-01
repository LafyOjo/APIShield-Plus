from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AffiliatePartnerCreate(BaseModel):
    name: str
    code: Optional[str] = None
    status: Optional[str] = None
    commission_type: str
    commission_value: float


class AffiliatePartnerUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    commission_type: Optional[str] = None
    commission_value: Optional[float] = None


class AffiliatePartnerRead(BaseModel):
    id: int
    name: str
    status: str
    code: str
    commission_type: str
    commission_value: float
    payout_method: str
    created_at: datetime
    updated_at: datetime


class AffiliateAttributionRead(BaseModel):
    id: int
    partner_id: int
    tenant_id: int
    first_touch_at: datetime
    last_touch_at: datetime
    source_meta: dict | None = None


class AffiliateCommissionRead(BaseModel):
    id: int
    partner_id: int
    tenant_id: int
    stripe_subscription_id: str | None = None
    amount: float
    currency: str
    status: str
    earned_at: datetime | None = None
    paid_at: datetime | None = None
    void_reason: str | None = None


class AffiliateLedgerUpdate(BaseModel):
    status: str
    paid_at: datetime | None = None
    void_reason: str | None = None


class AffiliateSummary(BaseModel):
    partner_id: int
    signups: int
    conversions: int
    commission_pending: float
    commission_earned: float
    commission_paid: float

