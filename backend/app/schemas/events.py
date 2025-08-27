from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class EventRead(BaseModel):
    id: int
    username: Optional[str]
    action: str
    success: bool
    timestamp: datetime

    class Config:
        orm_mode = True
