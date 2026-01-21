from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.anomaly_signals import AnomalySignalEvent
from app.models.incidents import (
    Incident,
    IncidentAnomalySignalLink,
    IncidentSecurityEventLink,
)
from app.models.security_events import SecurityEvent


INCIDENT_WINDOW_MINUTES = 30

SECURITY_CATEGORY_MAP = {
    "login": "login",
    "threat": "threat",
    "integrity": "integrity",
    "bot": "threat",
    "anomaly": "mixed",
}

ANOMALY_CATEGORY_MAP = {
    "js_error_event": "integrity",
}

SEVERITY_RANK = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


def _normalize_severity(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    return normalized if normalized in SEVERITY_RANK else "low"


def _infer_incident_category(category: str | None) -> str:
    normalized = (category or "").strip().lower()
    if not normalized:
        return "mixed"
    return SECURITY_CATEGORY_MAP.get(normalized, "mixed")


def _infer_anomaly_category(signal_type: str | None) -> str:
    normalized = (signal_type or "").strip().lower()
    return ANOMALY_CATEGORY_MAP.get(normalized, "mixed")


def _extract_request_path(summary: dict[str, Any] | None) -> str | None:
    if not summary:
        return None
    path = summary.get("path")
    if not path or not isinstance(path, str):
        return None
    return path


def _event_timestamp(value: SecurityEvent | AnomalySignalEvent) -> datetime:
    if isinstance(value, SecurityEvent):
        return value.event_ts or value.created_at
    return value.created_at


def _candidate_incidents(
    db: Session,
    *,
    tenant_id: int,
    website_id: int | None,
    environment_id: int | None,
    category: str,
    observed_at: datetime,
) -> list[Incident]:
    window_start = observed_at - timedelta(minutes=INCIDENT_WINDOW_MINUTES)
    query = (
        db.query(Incident)
        .filter(
            Incident.tenant_id == tenant_id,
            Incident.website_id == website_id,
            Incident.category == category,
            Incident.last_seen_at >= window_start,
            Incident.status != "resolved",
        )
        .order_by(Incident.last_seen_at.desc())
    )
    if environment_id is not None:
        query = query.filter(Incident.environment_id == environment_id)
    return query.all()


def _matches_incident(
    incident: Incident,
    *,
    ip_hash: str | None,
    request_path: str | None,
) -> bool:
    if ip_hash and incident.primary_ip_hash == ip_hash:
        return True
    if request_path:
        evidence = incident.evidence_json or {}
        paths = evidence.get("request_paths", {})
        if isinstance(paths, dict) and request_path in paths:
            return True
    return False


def _update_evidence(
    evidence: dict[str, Any] | None,
    *,
    source: str,
    event_type: str | None = None,
    signal_type: str | None = None,
    request_path: str | None = None,
) -> dict[str, Any]:
    updated = dict(evidence or {})
    counts = updated.setdefault("counts", {})
    counts[source] = int(counts.get(source, 0)) + 1
    if event_type:
        types = updated.setdefault("event_types", {})
        types[event_type] = int(types.get(event_type, 0)) + 1
    if signal_type:
        types = updated.setdefault("signal_types", {})
        types[signal_type] = int(types.get(signal_type, 0)) + 1
    if request_path:
        paths = updated.setdefault("request_paths", {})
        paths[request_path] = int(paths.get(request_path, 0)) + 1
    return updated


def _apply_signal_to_incident(
    incident: Incident,
    *,
    observed_at: datetime,
    category: str,
    severity: str,
    ip_hash: str | None,
    country_code: str | None,
    evidence: dict[str, Any],
) -> None:
    if incident.first_seen_at is None or observed_at < incident.first_seen_at:
        incident.first_seen_at = observed_at
    if incident.last_seen_at is None or observed_at > incident.last_seen_at:
        incident.last_seen_at = observed_at
    if incident.category != category:
        incident.category = "mixed"
    if SEVERITY_RANK.get(severity, 0) > SEVERITY_RANK.get(incident.severity, 0):
        incident.severity = severity
    if not incident.primary_ip_hash and ip_hash:
        incident.primary_ip_hash = ip_hash
    if not incident.primary_country_code and country_code:
        incident.primary_country_code = country_code
    incident.evidence_json = evidence


def attach_signal_to_incident(
    db: Session,
    *,
    incident: Incident,
    signal: SecurityEvent | AnomalySignalEvent,
) -> Incident:
    observed_at = _event_timestamp(signal)
    if isinstance(signal, SecurityEvent):
        category = _infer_incident_category(signal.category)
        severity = _normalize_severity(signal.severity)
        ip_hash = signal.ip_hash
        request_path = signal.request_path
        country_code = signal.country_code
        evidence = _update_evidence(
            incident.evidence_json,
            source="security_events",
            event_type=signal.event_type,
            request_path=request_path,
        )
        exists = (
            db.query(IncidentSecurityEventLink)
            .filter(
                IncidentSecurityEventLink.incident_id == incident.id,
                IncidentSecurityEventLink.security_event_id == signal.id,
            )
            .first()
        )
        if not exists:
            db.add(
                IncidentSecurityEventLink(
                    incident_id=incident.id,
                    security_event_id=signal.id,
                )
            )
    else:
        category = _infer_anomaly_category(signal.signal_type)
        severity = _normalize_severity(signal.severity)
        ip_hash = None
        request_path = _extract_request_path(signal.summary or {})
        country_code = None
        evidence = _update_evidence(
            incident.evidence_json,
            source="anomaly_signals",
            signal_type=signal.signal_type,
            request_path=request_path,
        )
        exists = (
            db.query(IncidentAnomalySignalLink)
            .filter(
                IncidentAnomalySignalLink.incident_id == incident.id,
                IncidentAnomalySignalLink.anomaly_signal_id == signal.id,
            )
            .first()
        )
        if not exists:
            db.add(
                IncidentAnomalySignalLink(
                    incident_id=incident.id,
                    anomaly_signal_id=signal.id,
                )
            )

    _apply_signal_to_incident(
        incident,
        observed_at=observed_at,
        category=category,
        severity=severity,
        ip_hash=ip_hash,
        country_code=country_code,
        evidence=evidence,
    )
    return incident


def create_incident_from_signal(
    db: Session,
    *,
    signal: SecurityEvent | AnomalySignalEvent,
) -> Incident:
    if isinstance(signal, SecurityEvent):
        tenant_id = signal.tenant_id
        website_id = signal.website_id
        environment_id = signal.environment_id
        category = _infer_incident_category(signal.category)
        severity = _normalize_severity(signal.severity)
        ip_hash = signal.ip_hash
        request_path = signal.request_path
        title = f"{category.replace('_', ' ').title()} incident"
        summary = f"Security event detected for {category}."
    else:
        tenant_id = signal.tenant_id
        website_id = signal.website_id
        environment_id = signal.environment_id
        category = _infer_anomaly_category(signal.signal_type)
        severity = _normalize_severity(signal.severity)
        ip_hash = None
        request_path = _extract_request_path(signal.summary or {})
        title = f"{category.replace('_', ' ').title()} anomaly"
        summary = "Anomaly signal detected."

    observed_at = _event_timestamp(signal)
    for candidate in _candidate_incidents(
        db,
        tenant_id=tenant_id,
        website_id=website_id,
        environment_id=environment_id,
        category=category,
        observed_at=observed_at,
    ):
        if _matches_incident(candidate, ip_hash=ip_hash, request_path=request_path):
            attach_signal_to_incident(db, incident=candidate, signal=signal)
            return candidate

    incident = Incident(
        tenant_id=tenant_id,
        website_id=website_id,
        environment_id=environment_id,
        status="open",
        category=category,
        title=title,
        summary=summary,
        severity=severity,
        first_seen_at=observed_at,
        last_seen_at=observed_at,
        primary_ip_hash=ip_hash,
        primary_country_code=getattr(signal, "country_code", None),
        evidence_json=None,
    )
    db.add(incident)
    db.flush()
    attach_signal_to_incident(db, incident=incident, signal=signal)
    return incident
