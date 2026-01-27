from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class RevenueLeakFactorSummary(BaseModel):
    factor_type: str
    severity: str
    count: int
    evidence: Optional[dict] = None


class RevenueLeakSeriesPoint(BaseModel):
    bucket_start: datetime
    estimated_lost_revenue: Optional[float] = None
    trust_score: Optional[int] = None
    confidence: Optional[float] = None


class RevenueLeakSummary(BaseModel):
    path: Optional[str] = None
    website_id: int
    environment_id: int
    total_lost_revenue: Optional[float] = None
    lost_conversions: float
    sessions: int
    observed_conversion_rate: float
    baseline_conversion_rate: Optional[float] = None
    trust_score_latest: Optional[int] = None
    trust_score_delta: Optional[int] = None
    confidence: Optional[float] = None
    top_factors: list[RevenueLeakFactorSummary] = []
    incident_ids: list[int] = []


class RevenueLeakResponse(BaseModel):
    items: list[RevenueLeakSummary]
    series: list[RevenueLeakSeriesPoint] = []
