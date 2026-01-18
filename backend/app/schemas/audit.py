from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel


class AuditEventType(str, Enum):
    """Allowed audit events for user actions."""

    user_login_success = "user_login_success"
    user_login_failure = "user_login_failure"
    user_logout = "user_logout"
    user_register = "user_register"


class AuditLogCreate(BaseModel):
    event: AuditEventType
    username: Optional[str] = None


class AuditLogRead(AuditLogCreate):
    id: int
    tenant_id: int
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
