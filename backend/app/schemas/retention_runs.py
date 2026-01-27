from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class RetentionRunRead(BaseModel):
    id: int
    tenant_id: int
    started_at: datetime
    finished_at: Optional[datetime]
    status: str
    event_retention_days: int
    raw_ip_retention_days: int
    behaviour_events_deleted: int
    security_events_deleted: int
    alerts_raw_ip_scrubbed: int
    events_raw_ip_scrubbed: int
    audit_logs_raw_ip_scrubbed: int
    security_events_raw_ip_scrubbed: int
    error_message: Optional[str]
    event_cutoff: Optional[datetime]
    raw_ip_cutoff: Optional[datetime]

    class Config:
        orm_mode = True
