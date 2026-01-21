from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class PrescriptionItemRead(BaseModel):
    id: int
    bundle_id: int
    incident_id: int
    key: str
    title: str
    priority: str
    effort: str
    expected_effect: str
    why_it_matters: Optional[str] = None
    steps: Optional[list[str]] = None
    status: str
    applied_at: Optional[datetime] = None
    dismissed_at: Optional[datetime] = None
    snoozed_until: Optional[datetime] = None
    notes: Optional[str] = None
    applied_by_user_id: Optional[int] = None
    evidence_json: Optional[dict] = None
    automation_possible: Optional[bool] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class PrescriptionItemUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    snoozed_until: Optional[datetime] = None
