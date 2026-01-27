from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ActivationMetricRead(BaseModel):
    tenant_id: int
    tenant_name: str
    tenant_slug: str
    tenant_created_at: datetime
    time_to_first_event_seconds: Optional[int] = None
    onboarding_completed_at: Optional[datetime] = None
    first_alert_created_at: Optional[datetime] = None
    first_incident_viewed_at: Optional[datetime] = None
    first_prescription_applied_at: Optional[datetime] = None
    activation_score: int = 0
    websites_count: int = 0
    alerts_count: int = 0
    incidents_count: int = 0
    last_event_at: Optional[datetime] = None
    days_since_last_event: Optional[int] = None


class ActivationSummary(BaseModel):
    total_tenants: int = 0
    tenants_with_events: int = 0
    tenants_onboarded: int = 0
    tenants_with_alerts: int = 0
    tenants_with_prescriptions: int = 0
    average_time_to_first_event_seconds: Optional[float] = None
    median_time_to_first_event_seconds: Optional[float] = None


class ActivationMetricsResponse(BaseModel):
    items: list[ActivationMetricRead]
    summary: ActivationSummary
