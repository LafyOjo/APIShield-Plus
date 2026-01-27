from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UserTourStateRead(BaseModel):
    user_id: int
    tenant_id: int
    tours_completed: list[str] = Field(default_factory=list)
    tours_dismissed: list[str] = Field(default_factory=list)
    last_updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True


class UserTourUpdate(BaseModel):
    complete: list[str] = Field(default_factory=list)
    dismiss: list[str] = Field(default_factory=list)
    reset: list[str] = Field(default_factory=list)
