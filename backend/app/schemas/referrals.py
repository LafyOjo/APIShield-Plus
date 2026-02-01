from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ReferralProgramConfigRead(BaseModel):
    is_enabled: bool
    reward_type: str
    reward_value: float
    eligibility_rules: dict
    fraud_limits: dict
    updated_at: datetime | None = None


class ReferralProgramConfigUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    reward_type: Optional[str] = None
    reward_value: Optional[float] = None
    eligibility_rules: Optional[dict] = None
    fraud_limits: Optional[dict] = None


class ReferralInviteCreate(BaseModel):
    max_uses: int | None = Field(default=None, ge=1)
    expires_in_days: int | None = Field(default=None, ge=1, le=365)
    expires_at: datetime | None = None


class ReferralInviteRead(BaseModel):
    id: int
    code: str
    status: str
    uses_count: int
    max_uses: int
    created_at: datetime
    expires_at: datetime | None
    share_url: Optional[str] = None


class ReferralRedemptionRead(BaseModel):
    id: int
    invite_id: int
    new_tenant_id: int
    status: str
    redeemed_at: datetime
    reward_applied_at: datetime | None = None
    reason: str | None = None


class ReferralSummary(BaseModel):
    credit_balance: float
    pending_redemptions: int
    applied_redemptions: int


class ReferralInviteResponse(BaseModel):
    invite: ReferralInviteRead
    share_url: str

