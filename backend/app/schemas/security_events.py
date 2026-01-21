from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SecurityEventListItem(BaseModel):
    id: int
    event_ts: Optional[datetime] = None
    created_at: Optional[datetime] = None
    event_type: str
    category: str
    severity: str
    request_path: Optional[str] = None
    status_code: Optional[int] = None
    ip_hash: Optional[str] = None
    website_id: Optional[int] = None
    environment_id: Optional[int] = None
    country_code: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    asn_number: Optional[int] = None
    asn_org: Optional[str] = None
    is_datacenter: Optional[bool] = None


class SecurityEventListResponse(BaseModel):
    items: list[SecurityEventListItem]
    total: int
    page: int
    page_size: int
