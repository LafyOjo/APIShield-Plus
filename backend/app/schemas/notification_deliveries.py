from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class NotificationDeliveryRead(BaseModel):
    id: int
    rule_id: int
    channel_id: int
    status: str
    created_at: datetime
    sent_at: Optional[datetime] = None
    dedupe_key: str
    payload_json: dict
    error_message: Optional[str] = None
    attempt_count: int

    class Config:
        orm_mode = True
        from_attributes = True
