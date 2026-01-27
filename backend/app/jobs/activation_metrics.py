from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.time import utcnow
from app.crud.activation_metrics import upsert_activation_metric
from app.models.activation_metrics import ActivationMetric
from app.models.behaviour_events import BehaviourEvent
from app.models.incidents import Incident
from app.models.notification_rules import NotificationRule
from app.models.onboarding_states import OnboardingState
from app.models.prescriptions import PrescriptionItem
from app.models.tenants import Tenant


def _normalize_completed_steps(state: OnboardingState | None) -> set[str]:
    if not state or not state.completed_steps_json:
        return set()
    if isinstance(state.completed_steps_json, list):
        return {str(value) for value in state.completed_steps_json}
    return set()


def _compute_activation_score(
    *,
    first_event_at: datetime | None,
    onboarding_completed_at: datetime | None,
    map_viewed_at: datetime | None,
    first_alert_created_at: datetime | None,
    first_prescription_applied_at: datetime | None,
) -> int:
    score = 0
    if first_event_at:
        score += 30
    if onboarding_completed_at:
        score += 20
    if map_viewed_at:
        score += 15
    if first_alert_created_at:
        score += 15
    if first_prescription_applied_at:
        score += 20
    return min(score, 100)


def _normalize_ts(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _churn_risk_for_last_event(last_event_at: datetime | None, now: datetime) -> tuple[str, int | None]:
    if not last_event_at:
        return "no_events", None
    days = max((now - last_event_at).days, 0)
    if days >= 14:
        return "high", days
    if days >= 7:
        return "medium", days
    return "low", days


def _first_event_at(db: Session, tenant_id: int) -> datetime | None:
    query = db.query(func.min(BehaviourEvent.ingested_at)).filter(
        BehaviourEvent.tenant_id == tenant_id
    )
    if hasattr(BehaviourEvent, "is_demo"):
        query = query.filter(BehaviourEvent.is_demo.is_(False))
    return query.scalar()


def _last_event_at(db: Session, tenant_id: int) -> datetime | None:
    query = db.query(func.max(BehaviourEvent.ingested_at)).filter(
        BehaviourEvent.tenant_id == tenant_id
    )
    if hasattr(BehaviourEvent, "is_demo"):
        query = query.filter(BehaviourEvent.is_demo.is_(False))
    return query.scalar()


def _first_alert_at(db: Session, tenant_id: int) -> datetime | None:
    return (
        db.query(func.min(NotificationRule.created_at))
        .filter(NotificationRule.tenant_id == tenant_id)
        .scalar()
    )


def _first_incident_at(db: Session, tenant_id: int) -> datetime | None:
    query = db.query(func.min(Incident.created_at)).filter(Incident.tenant_id == tenant_id)
    if hasattr(Incident, "is_demo"):
        query = query.filter(Incident.is_demo.is_(False))
    return query.scalar()


def _first_prescription_applied_at(db: Session, tenant_id: int) -> datetime | None:
    query = (
        db.query(func.min(PrescriptionItem.applied_at))
        .join(Incident, PrescriptionItem.incident_id == Incident.id)
        .filter(
            PrescriptionItem.tenant_id == tenant_id,
            PrescriptionItem.applied_at.isnot(None),
        )
    )
    if hasattr(Incident, "is_demo"):
        query = query.filter(Incident.is_demo.is_(False))
    return query.scalar()


def compute_activation_metric_for_tenant(db: Session, tenant: Tenant) -> ActivationMetric | None:
    if tenant.is_demo_mode:
        return None

    now = _normalize_ts(utcnow()) or datetime.utcnow()
    first_event_at = _normalize_ts(_first_event_at(db, tenant.id))
    last_event_at = _normalize_ts(_last_event_at(db, tenant.id))
    first_alert_created_at = _normalize_ts(_first_alert_at(db, tenant.id))
    first_incident_viewed_at = _normalize_ts(_first_incident_at(db, tenant.id))
    first_prescription_applied_at = _normalize_ts(_first_prescription_applied_at(db, tenant.id))

    onboarding_state = (
        db.query(OnboardingState).filter(OnboardingState.tenant_id == tenant.id).first()
    )
    completed_steps = _normalize_completed_steps(onboarding_state)
    onboarding_completed_at = None
    map_viewed_at = None
    if onboarding_state:
        if "finish" in completed_steps:
            onboarding_completed_at = _normalize_ts(
                onboarding_state.last_updated_at or onboarding_state.updated_at
            )
        if "enable_geo_map" in completed_steps:
            map_viewed_at = _normalize_ts(
                onboarding_state.last_updated_at or onboarding_state.updated_at
            )

    time_to_first_event_seconds = None
    tenant_created_at = _normalize_ts(tenant.created_at) if tenant.created_at else None
    if first_event_at and tenant_created_at:
        delta = first_event_at - tenant_created_at
        time_to_first_event_seconds = max(int(delta.total_seconds()), 0)

    activation_score = _compute_activation_score(
        first_event_at=first_event_at,
        onboarding_completed_at=onboarding_completed_at,
        map_viewed_at=map_viewed_at,
        first_alert_created_at=first_alert_created_at,
        first_prescription_applied_at=first_prescription_applied_at,
    )

    churn_risk, days_since_last_event = _churn_risk_for_last_event(last_event_at, now)

    notes_json = {
        "map_viewed_at": map_viewed_at.isoformat() if map_viewed_at else None,
        "map_viewed_source": "onboarding_step" if map_viewed_at else None,
        "last_event_at": last_event_at.isoformat() if last_event_at else None,
        "days_since_last_event": days_since_last_event,
        "churn_risk": churn_risk,
        "incident_view_source": "created_at",
    }

    return upsert_activation_metric(
        db,
        tenant_id=tenant.id,
        time_to_first_event_seconds=time_to_first_event_seconds,
        onboarding_completed_at=onboarding_completed_at,
        first_alert_created_at=first_alert_created_at,
        first_incident_viewed_at=first_incident_viewed_at,
        first_prescription_applied_at=first_prescription_applied_at,
        activation_score=activation_score,
        notes_json=notes_json,
    )


def run_activation_metrics_job(db: Session, *, tenant_id: int | None = None) -> int:
    query = db.query(Tenant)
    if tenant_id is not None:
        query = query.filter(Tenant.id == tenant_id)
    tenants = query.all()
    updated = 0
    for tenant in tenants:
        if compute_activation_metric_for_tenant(db, tenant):
            updated += 1
    return updated


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute activation metrics.")
    parser.add_argument("--tenant-id", type=int, default=None, help="Tenant ID to compute.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    with SessionLocal() as db:
        run_activation_metrics_job(db, tenant_id=args.tenant_id)


if __name__ == "__main__":
    main()
