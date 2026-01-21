from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class NotificationRuleCreate(BaseModel):
    name: str
    trigger_type: str
    is_enabled: Optional[bool] = True
    filters_json: Optional[dict] = None
    thresholds_json: Optional[dict] = None
    quiet_hours_json: Optional[dict] = None
    route_to_channel_ids: Optional[list[int]] = None


class NotificationRuleUpdate(BaseModel):
    name: Optional[str] = None
    trigger_type: Optional[str] = None
    is_enabled: Optional[bool] = None
    filters_json: Optional[dict] = None
    thresholds_json: Optional[dict] = None
    quiet_hours_json: Optional[dict] = None
    route_to_channel_ids: Optional[list[int]] = None


class NotificationRuleRead(BaseModel):
    id: int
    name: str
    trigger_type: str
    is_enabled: bool
    filters_json: Optional[dict] = None
    thresholds_json: Optional[dict] = None
    quiet_hours_json: Optional[dict] = None
    route_to_channel_ids: Optional[list[int]] = None
    created_by_user_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
        from_attributes = True
