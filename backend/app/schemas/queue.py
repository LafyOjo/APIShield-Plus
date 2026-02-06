from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class JobDeadLetterRead(BaseModel):
    id: int
    original_job_id: Optional[int]
    queue_name: str
    job_type: str
    tenant_id: Optional[int]
    attempt_count: int
    last_error: Optional[str]
    last_attempt_at: Optional[datetime]
    failed_at: datetime
    created_at: datetime

    class Config:
        orm_mode = True
