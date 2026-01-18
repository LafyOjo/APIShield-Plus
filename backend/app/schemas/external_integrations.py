from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ExternalIntegrationCreate(BaseModel):
    type: str
    config: dict
    status: Optional[str] = None


class ExternalIntegrationUpdate(BaseModel):
    config: Optional[dict] = None
    status: Optional[str] = None


class ExternalIntegrationRead(BaseModel):
    id: int
    type: str
    status: str
    last_error: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
