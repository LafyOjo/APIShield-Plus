from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class EventRead(BaseModel):
    id: int
    username: Optional[str]
    action: str
    success: bool
    timestamp: datetime
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

    class Config:
        orm_mode = True
