from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SecurityIpBreakdown(BaseModel):
    event: int = 0
    alert: int = 0
    audit: int = 0


class SecurityIpSummary(BaseModel):
    ip_hash: str
    total_count: int
    last_seen: datetime
    breakdown: SecurityIpBreakdown
    masked_ip: Optional[str] = None
    client_ip: Optional[str] = None


class SecurityIpSummaryResponse(BaseModel):
    items: list[SecurityIpSummary]
    total: int
    page: int
    page_size: int


class SecurityLocationSummary(BaseModel):
    country_code: str
    count: int
    last_seen: datetime


class SecurityLocationSummaryResponse(BaseModel):
    items: list[SecurityLocationSummary]
    total: int
    page: int
    page_size: int
