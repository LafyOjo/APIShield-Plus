from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.anomaly_signals import AnomalySignalEvent
from app.models.incidents import Incident, IncidentRecovery
from app.models.prescriptions import PrescriptionItem
from app.models.revenue_impact import ImpactEstimate
from app.models.security_events import SecurityEvent


STATUS_RANKS = {
    "open": 0,
    "investigating": 1,
    "mitigated": 2,
    "resolved": 3,
}

SECURITY_CATEGORIES = {"login", "threat", "integrity", "bot"}


def _normalize_ts(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _status_rank(value: str | None) -> int:
    if not value:
        return -1
    return STATUS_RANKS.get(value.lower(), -1)


def _applied_prescriptions(db: Session, incident: Incident) -> int:
    return int(
        db.query(func.count(PrescriptionItem.id))
        .filter(
            PrescriptionItem.tenant_id == incident.tenant_id,
            PrescriptionItem.incident_id == incident.id,
            PrescriptionItem.status == "applied",
            PrescriptionItem.applied_at.isnot(None),
        )
        .scalar()
        or 0
    )


def _recent_security_events(
    db: Session,
    *,
    incident: Incident,
    since: datetime,
) -> int:
    timestamp_col = func.coalesce(SecurityEvent.event_ts, SecurityEvent.created_at)
    query = (
        db.query(func.count(SecurityEvent.id))
        .filter(
            SecurityEvent.tenant_id == incident.tenant_id,
            timestamp_col >= since,
        )
    )
    if incident.website_id is not None:
        query = query.filter(SecurityEvent.website_id == incident.website_id)
    if incident.environment_id is not None:
        query = query.filter(SecurityEvent.environment_id == incident.environment_id)
    category = (incident.category or "").lower()
    if category in SECURITY_CATEGORIES:
        query = query.filter(SecurityEvent.category == category)
    return int(query.scalar() or 0)


def _recent_anomaly_signals(
    db: Session,
    *,
    incident: Incident,
    since: datetime,
) -> int:
    category = (incident.category or "").lower()
    if category not in {"integrity", "anomaly", "mixed"}:
        return 0
    query = (
        db.query(func.count(AnomalySignalEvent.id))
        .filter(
            AnomalySignalEvent.tenant_id == incident.tenant_id,
            AnomalySignalEvent.created_at >= since,
        )
    )
    if incident.website_id is not None:
        query = query.filter(AnomalySignalEvent.website_id == incident.website_id)
    if incident.environment_id is not None:
        query = query.filter(AnomalySignalEvent.environment_id == incident.environment_id)
    return int(query.scalar() or 0)


def _impact_triggers_investigation(impact: ImpactEstimate | None) -> bool:
    if not impact:
        return False
    delta_rate = float(impact.delta_rate or 0.0)
    return delta_rate >= settings.INCIDENT_INVESTIGATING_DELTA_RATE


def _should_investigate(incident: Incident, impact: ImpactEstimate | None) -> bool:
    severity = (incident.severity or "").lower()
    if severity in {"high", "critical"}:
        return True
    return _impact_triggers_investigation(impact)


def _should_mitigate(
    db: Session,
    *,
    incident: Incident,
    recovery: IncidentRecovery | None,
    recovery_threshold: float,
) -> bool:
    if recovery is None:
        return False
    applied_count = _applied_prescriptions(db, incident)
    error_drop = float(recovery.change_in_errors or 0.0)
    threat_drop = float(recovery.change_in_threats or 0.0)
    if applied_count > 0 and recovery.recovery_ratio >= recovery_threshold:
        return True
    if error_drop >= settings.INCIDENT_MITIGATION_ERROR_DROP:
        return True
    if threat_drop >= settings.INCIDENT_MITIGATION_THREAT_DROP:
        return True
    return False


def _should_resolve(
    db: Session,
    *,
    incident: Incident,
    impact: ImpactEstimate | None,
    recovery: IncidentRecovery | None,
    now: datetime,
) -> bool:
    if impact is None or recovery is None:
        return False
    baseline_rate = float(impact.baseline_rate or 0.0)
    post_rate = float(recovery.post_conversion_rate or 0.0)
    tolerance = settings.INCIDENT_RESOLVE_CONVERSION_TOLERANCE
    if abs(post_rate - baseline_rate) > tolerance:
        return False
    cooldown_hours = max(1, int(settings.INCIDENT_RESOLVE_COOLDOWN_HOURS))
    since = now - timedelta(hours=cooldown_hours)
    if _recent_security_events(db, incident=incident, since=since) > 0:
        return False
    if _recent_anomaly_signals(db, incident=incident, since=since) > 0:
        return False
    return True


def evaluate_status_transition(
    db: Session,
    incident: Incident,
    *,
    impact: ImpactEstimate | None = None,
    recovery: IncidentRecovery | None = None,
    now: datetime | None = None,
    allow_reopen: bool = False,
    mitigation_recovery_ratio: float | None = None,
) -> str | None:
    current = (incident.status or "open").lower()
    now = _normalize_ts(now or datetime.utcnow()) or datetime.utcnow()

    if impact is None and incident.impact_estimate_id:
        impact = (
            db.query(ImpactEstimate)
            .filter(
                ImpactEstimate.id == incident.impact_estimate_id,
                ImpactEstimate.tenant_id == incident.tenant_id,
            )
            .first()
        )
    if recovery is None:
        recovery = (
            db.query(IncidentRecovery)
            .filter(
                IncidentRecovery.incident_id == incident.id,
                IncidentRecovery.tenant_id == incident.tenant_id,
            )
            .order_by(IncidentRecovery.measured_at.desc())
            .first()
        )

    recovery_threshold = mitigation_recovery_ratio
    if recovery_threshold is None:
        recovery_threshold = settings.INCIDENT_MITIGATION_RECOVERY_RATIO

    next_status = None
    if current == "open":
        if _should_investigate(incident, impact):
            next_status = "investigating"
    elif current == "investigating":
        if _should_mitigate(
            db,
            incident=incident,
            recovery=recovery,
            recovery_threshold=recovery_threshold,
        ):
            next_status = "mitigated"
    elif current == "mitigated":
        if _should_resolve(db, incident=incident, impact=impact, recovery=recovery, now=now):
            next_status = "resolved"
    elif current == "resolved" and allow_reopen:
        if _should_investigate(incident, impact):
            next_status = "investigating"

    if next_status and incident.status_manual:
        if _status_rank(next_status) < _status_rank(current):
            return None

    return next_status
