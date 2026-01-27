from datetime import datetime
from typing import Optional

from pydantic import BaseModel, validator

from app.stack.constants import STACK_TYPES


class WebsiteStackProfileRead(BaseModel):
    website_id: int
    stack_type: str
    confidence: float
    manual_override: bool
    detected_signals_json: Optional[dict] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class WebsiteStackProfileUpdate(BaseModel):
    stack_type: Optional[str] = None
    manual_override: Optional[bool] = None

    @validator("stack_type")
    def validate_stack_type(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = value.strip().lower()
        if normalized not in STACK_TYPES:
            raise ValueError("Invalid stack_type.")
        return normalized
