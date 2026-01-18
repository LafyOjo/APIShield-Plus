from datetime import datetime, timedelta, timezone


ALLOWED_RETENTION_EVENT_TYPES = {
    "audit_log",
    "alert",
    "event",
    "behaviour_event",
    "integrity_anomaly",
}

DEFAULT_RETENTION_DAYS = {
    "audit_log": 90,
    "alert": 30,
    "event": 30,
    "behaviour_event": 7,
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
