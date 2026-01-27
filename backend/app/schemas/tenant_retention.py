from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class TenantRetentionPolicyRead(BaseModel):
    dataset_key: str
    retention_days: int
    is_legal_hold_enabled: bool
    legal_hold_reason: Optional[str]
    legal_hold_enabled_at: Optional[datetime]
    updated_at: datetime
    updated_by_user_id: Optional[int]

    class Config:
        orm_mode = True


class TenantRetentionPolicyUpdate(BaseModel):
    dataset_key: str
    retention_days: Optional[int] = None
    is_legal_hold_enabled: Optional[bool] = None
    legal_hold_reason: Optional[str] = None
