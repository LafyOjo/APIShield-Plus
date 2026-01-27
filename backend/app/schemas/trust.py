from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class TrustSnapshotRead(BaseModel):
    website_id: int
    environment_id: int
    bucket_start: datetime
    path: Optional[str] = None
    trust_score: int
    confidence: float
    factor_count: int

    class Config:
        orm_mode = True
