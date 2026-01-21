from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class NotificationChannelCreate(BaseModel):
    type: str
    name: str
    is_enabled: Optional[bool] = True
    config_public_json: Optional[dict] = None
    config_secret: Optional[dict] = None
    categories_allowed: Optional[list[str]] = None


class NotificationChannelUpdate(BaseModel):
    name: Optional[str] = None
    is_enabled: Optional[bool] = None
    config_public_json: Optional[dict] = None
    config_secret: Optional[dict] = None
    categories_allowed: Optional[list[str]] = None
    last_tested_at: Optional[datetime] = None
    last_error: Optional[str] = None


class NotificationChannelRead(BaseModel):
    id: int
    type: str
    name: str
    is_enabled: bool
    is_configured: bool
    config_public_json: Optional[dict] = None
    categories_allowed: Optional[list[str]] = None
    last_tested_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_by_user_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
        from_attributes = True
