# app/schemas/alerts.py
from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class AlertRead(BaseModel):
    id: int
    ip_address: str
    client_ip: Optional[str] = None
    ip_hash: Optional[str] = None
    user_agent: Optional[str] = None
    request_path: Optional[str] = None
    referrer: Optional[str] = None
    country_code: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    asn: Optional[str] = None
    is_datacenter: Optional[bool] = None
    timestamp: datetime
    total_fails: int
    detail: Optional[str]

    class Config:
        orm_mode = True


class AlertStat(BaseModel):
    time: datetime
    invalid: int
    blocked: int
