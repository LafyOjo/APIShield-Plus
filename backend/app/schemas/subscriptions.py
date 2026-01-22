from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SubscriptionRead(BaseModel):
    id: int
    tenant_id: int
    plan_id: int
    plan_key: Optional[str] = None
    provider: str
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    status: str
    current_period_start: Optional[datetime]
    current_period_end: Optional[datetime]
    cancel_at_period_end: bool
    seats: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
