from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class TenantUsageRead(BaseModel):
    tenant_id: int
    period_start: datetime
    period_end: Optional[datetime]
    events_ingested: int
    storage_bytes: int

    class Config:
        orm_mode = True
