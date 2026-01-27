from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class ProtectionPresetRead(BaseModel):
    id: int
    incident_id: int
    website_id: Optional[int] = None
    preset_type: str
    content_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
