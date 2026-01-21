from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.revenue_impact import compute_impact
from app.insights.interpretation import _extract_paths, _infer_metric_key, _window_stats
from app.models.incidents import Incident, IncidentRecovery
from app.models.prescriptions import PrescriptionItem
from app.models.revenue_impact import ImpactEstimate
from app.models.security_events import SecurityEvent


MIN_POST_WINDOW_HOURS = 2
MAX_POST_WINDOW_HOURS = 24
DEFAULT_POST_WINDOW_HOURS = 6
MIN_RECOVERY_SESSIONS = 20

SECURITY_CATEGORIES = {"login", "threat", "integrity", "bot"}


def _normalize_ts(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _clamp_window_hours(value: int | None) -> int:
    try:
        hours = int(value or DEFAULT_POST_WINDOW_HOURS)
    except (TypeError, ValueError):
        hours = DEFAULT_POST_WINDOW_HOURS
    return max(MIN_POST_WINDOW_HOURS, min(MAX_POST_WINDOW_HOURS, hours))


def _first_applied_at(db: Session, incident: Incident) -> datetime | None:
    return (
        db.query(func.min(PrescriptionItem.applied_at))
        .filter(
            PrescriptionItem.incident_id == incident.id,
            PrescriptionItem.tenant_id == incident.tenant_id,
            PrescriptionItem.status == "applied",
            PrescriptionItem.applied_at.isnot(None),
        )
        .scalar()
    )


def _security_event_count(
    db: Session,
    *,
    incident: Incident,
    from_ts: datetime,
    to_ts: datetime,
    category: str | None,
) -> int:
    timestamp_col = func.coalesce(SecurityEvent.event_ts, SecurityEvent.created_at)
    query = (
        db.query(func.count(SecurityEvent.id))
        .filter(
            SecurityEvent.tenant_id == incident.tenant_id,
            timestamp_col >= from_ts,
            timestamp_col <= to_ts,
        )
    )
    if incident.website_id is not None:
        query = query.filter(SecurityEvent.website_id == incident.website_id)
    if incident.environment_id is not None:
        query = query.filter(SecurityEvent.environment_id == incident.environment_id)
    if category:
        query = query.filter(SecurityEvent.category == category)
    return int(query.scalar() or 0)


def _score_confidence(
    *,
    post_sessions: int,
    recovery_ratio: float,
    change_in_errors: float | None,
    change_in_threats: float | None,
) -> float:
    score = 0.2
    if post_sessions >= 50:
        score += 0.2
    if recovery_ratio >= 0.5:
        score += 0.2
    if change_in_errors is not None and change_in_errors >= 0.05:
        score += 0.1
    if change_in_threats is not None and change_in_threats > 0:
        score += 0.1
    return min(score, 0.9)


def compute_recovery(
    db: Session,
    incident_id: int,
    *,
    window_hours: int = DEFAULT_POST_WINDOW_HOURS,
    force: bool = False,
) -> dict[str, Any] | None:
    incident = (
        db.query(Incident)
        .filter(Incident.id == incident_id)
        .first()
    )
    if not incident or incident.impact_estimate_id is None:
        return None

    impact = (
        db.query(ImpactEstimate)
        .filter(
            ImpactEstimate.id == incident.impact_estimate_id,
            ImpactEstimate.tenant_id == incident.tenant_id,
        )
        .first()
    )
    if impact is None:
        return None

    applied_at = _normalize_ts(_first_applied_at(db, incident))
    if applied_at is None:
        return None

    start = applied_at
    now = _normalize_ts(datetime.utcnow()) or applied_at
    hours = _clamp_window_hours(window_hours)
    end = start + timedelta(hours=hours)
    if end > now:
        end = now
    if end <= start:
        return None

    duration_hours = (end - start).total_seconds() / 3600.0
    if duration_hours < MIN_POST_WINDOW_HOURS:
        return None

    latest = (
        db.query(IncidentRecovery)
        .filter(
            IncidentRecovery.incident_id == incident.id,
            IncidentRecovery.tenant_id == incident.tenant_id,
        )
        .order_by(IncidentRecovery.measured_at.desc())
        .first()
    )
    if latest and not force:
        if latest.window_start == start and latest.window_end == end:
            return None

    paths = _extract_paths(incident)
    metric_key = _infer_metric_key(incident, paths)

    incident_start = _normalize_ts(incident.first_seen_at)
    incident_end = _normalize_ts(incident.last_seen_at)
    if not incident_start or not incident_end:
        return None
    if incident_end < incident_start:
        incident_start, incident_end = incident_end, incident_start

    incident_stats = _window_stats(
        db,
        tenant_id=incident.tenant_id,
        website_id=incident.website_id,
        environment_id=incident.environment_id,
        from_ts=incident_start,
        to_ts=incident_end,
        paths=paths,
    )
    post_stats = _window_stats(
        db,
        tenant_id=incident.tenant_id,
        website_id=incident.website_id,
        environment_id=incident.environment_id,
        from_ts=start,
        to_ts=end,
        paths=paths,
    )

    post_sessions = int(post_stats.get("view_sessions") or 0)
    if post_sessions < MIN_RECOVERY_SESSIONS:
        return None

    incident_rate = float(impact.observed_rate or 0.0)
    baseline_rate = float(impact.baseline_rate or 0.0)
    post_rate = float(post_stats.get("conversion_rate") or 0.0)

    denom = baseline_rate - incident_rate
    if denom <= 0:
        recovery_ratio = 0.0
    else:
        recovery_ratio = (post_rate - incident_rate) / denom
    recovery_ratio = max(0.0, min(1.0, recovery_ratio))

    incident_error_rate = float(incident_stats.get("error_rate") or 0.0)
    post_error_rate = float(post_stats.get("error_rate") or 0.0)
    change_in_errors = incident_error_rate - post_error_rate

    category = (incident.category or "").lower()
    category_filter = category if category in SECURITY_CATEGORIES else None
    incident_threats = _security_event_count(
        db,
        incident=incident,
        from_ts=incident_start,
        to_ts=incident_end,
        category=category_filter,
    )
    post_threats = _security_event_count(
        db,
        incident=incident,
        from_ts=start,
        to_ts=end,
        category=category_filter,
    )
    change_in_threats = float(incident_threats - post_threats)

    post_impact = compute_impact(
        observed_rate=post_rate,
        baseline_rate=baseline_rate,
        sessions=post_sessions,
    )

    confidence = _score_confidence(
        post_sessions=post_sessions,
        recovery_ratio=recovery_ratio,
        change_in_errors=change_in_errors,
        change_in_threats=change_in_threats,
    )

    evidence = {
        "metric_key": metric_key,
        "paths": paths,
        "window": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "duration_hours": round(duration_hours, 2),
        },
        "incident": {
            "conversion_rate": incident_rate,
            "error_rate": incident_error_rate,
            "threat_count": incident_threats,
        },
        "post": {
            "sessions": post_sessions,
            "conversion_rate": post_rate,
            "error_rate": post_error_rate,
            "threat_count": post_threats,
        },
        "baseline_rate": baseline_rate,
        "post_impact": post_impact,
    }

    recovery = IncidentRecovery(
        tenant_id=incident.tenant_id,
        website_id=incident.website_id,
        environment_id=incident.environment_id,
        incident_id=incident.id,
        measured_at=_normalize_ts(datetime.utcnow()) or start,
        window_start=start,
        window_end=end,
        post_conversion_rate=post_rate,
        change_in_errors=change_in_errors,
        change_in_threats=change_in_threats,
        recovery_ratio=recovery_ratio,
        confidence=confidence,
        evidence_json=evidence,
    )
    db.add(recovery)
    db.flush()

    return {
        "recovery": recovery,
        "post_impact": post_impact,
        "recovery_ratio": recovery_ratio,
        "evidence": evidence,
    }
