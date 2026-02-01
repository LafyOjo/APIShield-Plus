from datetime import date
from typing import Any

from pydantic import BaseModel


class GrowthSnapshotRead(BaseModel):
    snapshot_date: date
    signups: int
    activated: int
    onboarding_completed: int
    first_incident: int
    first_prescription: int
    upgraded: int
    churned: int
    avg_time_to_first_event_seconds: float | None = None
    funnel: dict[str, Any] | None = None
    cohorts: list[dict[str, Any]] | None = None
    paywall: list[dict[str, Any]] | None = None


class ChurnRiskItem(BaseModel):
    tenant_id: int
    tenant_name: str
    tenant_slug: str
    days_since_last_event: int | None = None
    days_since_last_login: int | None = None
    open_incidents: int = 0
    risk_level: str


class GrowthDashboardResponse(BaseModel):
    snapshots: list[GrowthSnapshotRead]
    latest: GrowthSnapshotRead | None = None
    cohorts: list[dict[str, Any]] = []
    paywall: list[dict[str, Any]] = []
    churn_risk: list[ChurnRiskItem] = []
