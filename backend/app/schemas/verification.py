from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class VerificationCheckItem(BaseModel):
    check_type: str
    label: Optional[str] = None
    status: str
    before: Optional[float] = None
    after: Optional[float] = None
    delta: Optional[float] = None
    threshold: Optional[float] = None
    unit: Optional[str] = None
    evidence: Optional[dict[str, Any]] = None


class VerificationCheckRunRead(BaseModel):
    id: int
    incident_id: int
    website_id: Optional[int] = None
    environment_id: Optional[int] = None
    status: str
    checks: list[VerificationCheckItem]
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
