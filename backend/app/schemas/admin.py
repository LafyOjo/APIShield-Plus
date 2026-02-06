from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class AdminTenantListItem(BaseModel):
    id: int
    name: str
    slug: str
    data_region: str
    created_region: str
    created_at: datetime
    deleted_at: Optional[datetime] = None


class AdminSubscriptionSummary(BaseModel):
    plan_name: Optional[str] = None
    status: Optional[str] = None
    current_period_end: Optional[datetime] = None


class AdminUsageSummary(BaseModel):
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    events_ingested: int = 0
    storage_bytes: int = 0
    websites_count: int = 0
    members_count: int = 0


class AdminHealthSummary(BaseModel):
    last_ingest_at: Optional[datetime] = None
    ingest_events_1h: int = 0
    ingest_events_24h: int = 0
    ingest_success_rate_1h: Optional[float] = None
    ingest_rate_limit_1h: int = 0
    security_events_1h: int = 0
    export_failures_7d: int = 0
    retention_failures_7d: int = 0
    notification_failures_24h: int = 0


class AdminTenantDetail(BaseModel):
    tenant: AdminTenantListItem
    subscription: AdminSubscriptionSummary
    entitlements: dict[str, Any]
    usage: AdminUsageSummary
    health: AdminHealthSummary


class AdminIncidentSummary(BaseModel):
    id: int
    status: str
    severity: str
    title: str
    last_seen_at: datetime


class AdminSupportViewAsRequest(BaseModel):
    tenant_id: int = Field(..., ge=1)
    reason: str = Field(..., min_length=3, max_length=500)


class AdminSupportViewAsResponse(BaseModel):
    tenant_id: int
    expires_at: datetime
    support_token: str


class AdminPerfRequestRecord(BaseModel):
    request_id: Optional[str] = None
    path: str
    status_code: int
    duration_ms: float
    db_time_ms: float
    db_queries_count: int
