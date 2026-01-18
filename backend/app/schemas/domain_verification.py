from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DomainVerificationStartRequest(BaseModel):
    method: str


class DomainVerificationCheckRequest(BaseModel):
    method: Optional[str] = None
    force_verify: bool = False


class DomainVerificationStartResponse(BaseModel):
    id: int
    method: str
    token: str
    status: str
    instructions: str


class DomainVerificationStatus(BaseModel):
    id: int
    method: str
    status: str
    created_at: datetime
    verified_at: Optional[datetime]
    last_checked_at: Optional[datetime]

    class Config:
        orm_mode = True
