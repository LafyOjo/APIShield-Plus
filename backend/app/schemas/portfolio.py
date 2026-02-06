from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class PortfolioWebsiteRead(BaseModel):
    website_id: int
    domain: str
    display_name: Optional[str] = None
    status: str
    stack_type: Optional[str] = None
    data_region: Optional[str] = None
    trust_score_current: Optional[int] = None
    trust_confidence: Optional[float] = None
    trust_verified: bool = False
    trust_updated_at: Optional[datetime] = None
    incidents_open_total: int = 0
    incidents_open_critical: int = 0
    revenue_leak_7d: float = 0.0
    last_incident_at: Optional[datetime] = None


class PortfolioIncidentSummary(BaseModel):
    incident_id: int
    website_id: Optional[int] = None
    title: str
    severity: str
    status: str
    category: str
    last_seen_at: datetime


class PortfolioLeakHotspot(BaseModel):
    website_id: Optional[int] = None
    path: Optional[str] = None
    estimated_lost_revenue: float


class PortfolioSummary(BaseModel):
    website_count: int
    avg_trust_score: Optional[float] = None
    open_incidents_total: int = 0
    open_incidents_critical: int = 0
    total_revenue_leak: float = 0.0
    top_incidents: list[PortfolioIncidentSummary] = []
    top_leak_paths: list[PortfolioLeakHotspot] = []
    range_notice: Optional[str] = None


class PortfolioSummaryResponse(BaseModel):
    summary: PortfolioSummary


class PortfolioExportResponse(BaseModel):
    generated_at: datetime
    items: list[PortfolioWebsiteRead]
