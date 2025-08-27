# app/schemas/alerts.py
from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class AlertRead(BaseModel):
    id: int
    ip_address: str
    timestamp: datetime
    total_fails: int
    detail: Optional[str]

    class Config:
        orm_mode = True


class AlertStat(BaseModel):
    time: datetime
    invalid: int
    blocked: int
