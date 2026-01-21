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

DEFAULT_RETENTION_DAYS = {
    "audit_log": 90,
    "alert": 30,
    "event": 30,
    "behaviour_event": 7,
    "security_event": 30,
}


def validate_event_type(event_type: str) -> None:
    if event_type not in ALLOWED_RETENTION_EVENT_TYPES:
        raise ValueError(f"Unsupported event_type: {event_type}")


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
