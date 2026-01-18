from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SubscriptionRead(BaseModel):
    id: int
    tenant_id: int
    plan_id: int
    provider: str
    status: str
    current_period_start: Optional[datetime]
    current_period_end: Optional[datetime]
    cancel_at_period_end: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
