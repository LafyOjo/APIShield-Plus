from typing import Optional

from pydantic import BaseModel


class TenantSettingsRead(BaseModel):
    timezone: str
    retention_days: int
    event_retention_days: int
    ip_raw_retention_days: int
    alert_prefs: dict

    class Config:
        orm_mode = True


class TenantSettingsUpdate(BaseModel):
    timezone: Optional[str] = None
    retention_days: Optional[int] = None
    event_retention_days: Optional[int] = None
    ip_raw_retention_days: Optional[int] = None
    alert_prefs: Optional[dict] = None
