from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DemoSeedRequest(BaseModel):
    force: bool = False


class DemoSeedResponse(BaseModel):
    tenant_id: int
    seeded_at: datetime
    expires_at: datetime
    counts: dict[str, int]
    demo_enabled: bool = True
    message: Optional[str] = None
