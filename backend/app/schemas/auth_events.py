from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AuthEventCreate(BaseModel):
    username: Optional[str] = None
    success: bool
    is_credential_stuffing: bool = False
    blocked: bool = False
    block_rule: Optional[str] = None
    action: str = "login"
    source: str = "api"


class AuthEventOut(BaseModel):
    id: int
    user: Optional[str]
    action: str
    success: bool
    source: str
    created_at: datetime

    class Config:
        from_attributes = True
