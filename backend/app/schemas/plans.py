from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class PlanRead(BaseModel):
    id: int
    name: str
    price_monthly: Optional[float]
    limits_json: dict
    features_json: dict
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class PlanCreate(BaseModel):
    name: str
    price_monthly: Optional[float] = None
    limits_json: Optional[dict] = None
    features_json: Optional[dict] = None
    is_active: bool = True


class PlanUpdate(BaseModel):
    name: Optional[str] = None
    price_monthly: Optional[float] = None
    limits_json: Optional[dict] = None
    features_json: Optional[dict] = None
    is_active: Optional[bool] = None
