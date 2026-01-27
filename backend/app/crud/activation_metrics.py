from sqlalchemy.orm import Session

from app.models.activation_metrics import ActivationMetric


def get_activation_metric(db: Session, tenant_id: int) -> ActivationMetric | None:
    return db.query(ActivationMetric).filter(ActivationMetric.tenant_id == tenant_id).first()


def upsert_activation_metric(
    db: Session,
    *,
    tenant_id: int,
    time_to_first_event_seconds: int | None,
    onboarding_completed_at,
    first_alert_created_at,
    first_incident_viewed_at,
    first_prescription_applied_at,
    activation_score: int,
    notes_json: dict | None,
) -> ActivationMetric:
    metric = get_activation_metric(db, tenant_id)
    if metric:
        metric.time_to_first_event_seconds = time_to_first_event_seconds
        metric.onboarding_completed_at = onboarding_completed_at
        metric.first_alert_created_at = first_alert_created_at
        metric.first_incident_viewed_at = first_incident_viewed_at
        metric.first_prescription_applied_at = first_prescription_applied_at
        metric.activation_score = activation_score
        metric.notes_json = notes_json
        db.commit()
        db.refresh(metric)
        return metric

    metric = ActivationMetric(
        tenant_id=tenant_id,
        time_to_first_event_seconds=time_to_first_event_seconds,
        onboarding_completed_at=onboarding_completed_at,
        first_alert_created_at=first_alert_created_at,
        first_incident_viewed_at=first_incident_viewed_at,
        first_prescription_applied_at=first_prescription_applied_at,
        activation_score=activation_score,
        notes_json=notes_json,
    )
    db.add(metric)
    db.commit()
    db.refresh(metric)
    return metric
