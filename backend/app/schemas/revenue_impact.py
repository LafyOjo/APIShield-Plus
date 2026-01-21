from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ImpactEstimateCreate(BaseModel):
    tenant_id: int
    website_id: Optional[int] = None
    environment_id: Optional[int] = None
    metric_key: str
    incident_id: Optional[str] = None
    window_start: datetime
    window_end: datetime
    observed_rate: float
    baseline_rate: float
    delta_rate: float
    estimated_lost_conversions: float
    estimated_lost_revenue: Optional[float] = None
    confidence: float
    explanation_json: Optional[dict] = None


class ImpactEstimateRead(ImpactEstimateCreate):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True
