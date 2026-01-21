from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.schemas.prescriptions import PrescriptionItemRead


class ImpactSummary(BaseModel):
    estimated_lost_revenue: Optional[float] = None
    estimated_lost_conversions: Optional[float] = None
    confidence: Optional[float] = None


class ImpactEstimateDetail(BaseModel):
    id: int
    metric_key: str
    window_start: datetime
    window_end: datetime
    observed_rate: float
    baseline_rate: float
    delta_rate: float
    estimated_lost_conversions: float
    estimated_lost_revenue: Optional[float] = None
    confidence: float
    explanation_json: Optional[dict] = None
    created_at: datetime

    class Config:
        orm_mode = True


class IncidentRecoveryRead(BaseModel):
    id: int
    measured_at: datetime
    window_start: datetime
    window_end: datetime
    post_conversion_rate: float
    change_in_errors: Optional[float] = None
    change_in_threats: Optional[float] = None
    recovery_ratio: float
    confidence: float
    evidence_json: Optional[dict] = None

    class Config:
        orm_mode = True


class PrescriptionBundleRead(BaseModel):
    id: int
    status: str
    created_at: datetime
    items: list[PrescriptionItemRead]
    notes: Optional[str] = None

    class Config:
        orm_mode = True


class IncidentListItem(BaseModel):
    id: int
    status: str
    category: str
    title: str
    severity: str
    first_seen_at: datetime
    last_seen_at: datetime
    website_id: Optional[int] = None
    environment_id: Optional[int] = None
    impact_estimate_id: Optional[int] = None
    primary_country_code: Optional[str] = None
    impact_summary: Optional[ImpactSummary] = None

    class Config:
        orm_mode = True


class IncidentRead(IncidentListItem):
    summary: Optional[str] = None
    notes: Optional[str] = None
    primary_ip_hash: Optional[str] = None
    evidence_json: Optional[dict] = None
    evidence_summary: Optional[dict] = None
    prescription_bundle_id: Optional[str] = None
    assigned_to_user_id: Optional[int] = None
    impact_estimate: Optional[ImpactEstimateDetail] = None
    recovery_measurement: Optional[IncidentRecoveryRead] = None
    prescription_bundle: Optional[PrescriptionBundleRead] = None
    map_link_params: Optional[dict] = None
    created_at: datetime
    updated_at: datetime


class IncidentUpdate(BaseModel):
    status: Optional[str] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    notes: Optional[str] = None
    severity: Optional[str] = None
    impact_estimate_id: Optional[int] = None
    prescription_bundle_id: Optional[str] = None
    assigned_to_user_id: Optional[int] = None
