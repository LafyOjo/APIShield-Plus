from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session


ALLOWED_RETENTION_EVENT_TYPES = {
    "audit_log",
    "alert",
    "event",
    "behaviour_event",
    "integrity_anomaly",
    "security_event",
}

ALLOWED_RETENTION_DATASETS = {
    "behaviour_events",
    "security_events",
    "incidents",
    "audit_logs",
    "geo_agg",
}

DATASET_RETENTION_LIMIT_KEYS = {
    "behaviour_events": "retention_days",
    "security_events": "retention_days",
    "incidents": "retention_days",
    "audit_logs": "retention_days",
    "geo_agg": "geo_history_days",
}

DEFAULT_RETENTION_DAYS = {
    "audit_log": 90,
    "alert": 30,
    "event": 30,
    "behaviour_event": 7,
    "security_event": 30,
}

DEFAULT_DATASET_RETENTION_DAYS = {
    "behaviour_events": 30,
    "security_events": 30,
    "incidents": 90,
    "audit_logs": 90,
    "geo_agg": 30,
}


def validate_event_type(event_type: str) -> None:
    if event_type not in ALLOWED_RETENTION_EVENT_TYPES:
        raise ValueError(f"Unsupported event_type: {event_type}")


def validate_dataset_key(dataset_key: str) -> None:
    if dataset_key not in ALLOWED_RETENTION_DATASETS:
        raise ValueError(f"Unsupported dataset_key: {dataset_key}")


def default_dataset_retention_days(
    dataset_key: str,
    *,
    plan_limits: dict | None = None,
) -> int:
    validate_dataset_key(dataset_key)
    limit_key = DATASET_RETENTION_LIMIT_KEYS.get(dataset_key)
    if plan_limits and limit_key:
        value = plan_limits.get(limit_key)
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = None
        if parsed and parsed > 0:
            return parsed
    fallback = DEFAULT_DATASET_RETENTION_DAYS.get(dataset_key)
    if fallback is None:
        raise ValueError(f"No default retention days configured for dataset: {dataset_key}")
    return fallback


def compute_purge_cutoff(event_type: str, days: int | None = None, *, now: datetime | None = None) -> datetime:
    validate_event_type(event_type)
    retention_days = days if days is not None else DEFAULT_RETENTION_DAYS.get(event_type)
    if retention_days is None:
        raise ValueError(f"No default retention days configured for event_type: {event_type}")
    if retention_days <= 0:
        raise ValueError("retention days must be positive")
    anchor = now or datetime.now(timezone.utc)
    return anchor - timedelta(days=retention_days)


def purge_old_behaviour_events(db: Session, tenant_id: int, cutoff: datetime) -> int:
    """
    Delete behaviour events older than the cutoff.

    Intended for scheduled cleanup jobs; not called inline with ingest.
    """
    if tenant_id is None:
        raise ValueError("tenant_id is required")
    if cutoff is None:
        raise ValueError("cutoff is required")
    from app.models.behaviour_events import BehaviourEvent

    deleted = (
        db.query(BehaviourEvent)
        .filter(
            BehaviourEvent.tenant_id == tenant_id,
            BehaviourEvent.ingested_at < cutoff,
        )
        .delete(synchronize_session=False)
    )
    db.commit()
    return int(deleted or 0)
