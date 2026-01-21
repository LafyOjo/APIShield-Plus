from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.entitlements import resolve_effective_entitlements
from app.models.incidents import Incident, IncidentRecovery, IncidentSecurityEventLink
from app.models.prescriptions import PrescriptionBundle, PrescriptionItem
from app.models.revenue_impact import ImpactEstimate
from app.models.security_events import SecurityEvent


GRANULARITY_LEVELS = {"country": 0, "city": 1, "asn": 2}
MAX_EVIDENCE_ITEMS = 8
MAX_GEO_ITEMS = 5


def _normalize_count(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _build_count_list(
    data: dict[str, Any] | None,
    key_name: str,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    items = []
    for raw_key, raw_value in data.items():
        if raw_key is None:
            continue
        key = str(raw_key).strip()
        if not key:
            continue
        count = _normalize_count(raw_value)
        if count <= 0:
            continue
        items.append((key, count))
    items.sort(key=lambda item: (-item[1], item[0]))
    return [{key_name: key, "count": count} for key, count in items[:limit]]


def _normalize_counts(data: dict[str, Any] | None) -> dict[str, int]:
    if not isinstance(data, dict):
        return {}
    normalized: dict[str, int] = {}
    for raw_key, raw_value in data.items():
        if raw_key is None:
            continue
        key = str(raw_key).strip()
        if not key:
            continue
        count = _normalize_count(raw_value)
        if count < 0:
            continue
        normalized[key] = count
    return normalized


def _query_top_countries(
    db: Session,
    *,
    tenant_id: int,
    incident_id: int,
    limit: int,
) -> list[dict[str, Any]]:
    rows = (
        db.query(
            SecurityEvent.country_code.label("country_code"),
            func.count(SecurityEvent.id).label("count"),
        )
        .join(
            IncidentSecurityEventLink,
            IncidentSecurityEventLink.security_event_id == SecurityEvent.id,
        )
        .filter(
            IncidentSecurityEventLink.incident_id == incident_id,
            SecurityEvent.tenant_id == tenant_id,
            SecurityEvent.country_code.isnot(None),
            SecurityEvent.country_code != "",
        )
        .group_by(SecurityEvent.country_code)
        .order_by(func.count(SecurityEvent.id).desc(), SecurityEvent.country_code.asc())
        .limit(limit)
        .all()
    )
    return [
        {"country_code": row.country_code, "count": int(row.count or 0)}
        for row in rows
    ]


def _query_top_asns(
    db: Session,
    *,
    tenant_id: int,
    incident_id: int,
    limit: int,
) -> list[dict[str, Any]]:
    rows = (
        db.query(
            SecurityEvent.asn_number.label("asn_number"),
            SecurityEvent.asn_org.label("asn_org"),
            func.count(SecurityEvent.id).label("count"),
        )
        .join(
            IncidentSecurityEventLink,
            IncidentSecurityEventLink.security_event_id == SecurityEvent.id,
        )
        .filter(
            IncidentSecurityEventLink.incident_id == incident_id,
            SecurityEvent.tenant_id == tenant_id,
            SecurityEvent.asn_number.isnot(None),
        )
        .group_by(SecurityEvent.asn_number, SecurityEvent.asn_org)
        .order_by(func.count(SecurityEvent.id).desc(), SecurityEvent.asn_number.asc())
        .limit(limit)
        .all()
    )
    return [
        {
            "asn_number": row.asn_number,
            "asn_org": row.asn_org,
            "count": int(row.count or 0),
        }
        for row in rows
    ]


def _build_prescription_items(
    db: Session,
    *,
    tenant_id: int,
    incident_id: int,
) -> list[dict[str, Any]]:
    bundle = (
        db.query(PrescriptionBundle)
        .filter(
            PrescriptionBundle.tenant_id == tenant_id,
            PrescriptionBundle.incident_id == incident_id,
        )
        .first()
    )
    if not bundle:
        return []

    template_map: dict[str, dict[str, Any]] = {}
    raw_items = bundle.items_json if isinstance(bundle.items_json, list) else []
    for raw in raw_items:
        if isinstance(raw, dict) and raw.get("id"):
            template_map[str(raw.get("id"))] = raw

    items = (
        db.query(PrescriptionItem)
        .filter(
            PrescriptionItem.bundle_id == bundle.id,
            PrescriptionItem.tenant_id == tenant_id,
        )
        .order_by(PrescriptionItem.id.asc())
        .all()
    )
    payload = []
    for item in items:
        template = template_map.get(item.key, {})
        payload.append(
            {
                "id": item.id,
                "key": item.key,
                "title": item.title,
                "priority": item.priority,
                "effort": item.effort,
                "expected_effect": item.expected_effect,
                "status": item.status,
                "applied_at": item.applied_at,
                "dismissed_at": item.dismissed_at,
                "snoozed_until": item.snoozed_until,
                "notes": item.notes,
                "why_it_matters": template.get("why_it_matters"),
                "steps": template.get("steps"),
            }
        )
    return payload


def assemble_incident_report(
    db: Session,
    *,
    incident: Incident,
    entitlements: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tenant_id = incident.tenant_id
    entitlements = entitlements or resolve_effective_entitlements(db, tenant_id)
    features = entitlements.get("features", {}) if entitlements else {}
    limits = entitlements.get("limits", {}) if entitlements else {}

    geo_enabled = bool(features.get("geo_map"))
    granularity_value = str(limits.get("geo_granularity") or "").lower()
    granularity_rank = GRANULARITY_LEVELS.get(
        granularity_value,
        GRANULARITY_LEVELS["city"],
    )
    allow_geo = geo_enabled
    allow_asn = geo_enabled and granularity_rank >= GRANULARITY_LEVELS["asn"]

    evidence = incident.evidence_json if isinstance(incident.evidence_json, dict) else {}
    evidence_counts = _normalize_counts(evidence.get("counts"))
    event_types = _build_count_list(
        evidence.get("event_types"),
        "event_type",
        limit=MAX_EVIDENCE_ITEMS,
    )
    signal_types = _build_count_list(
        evidence.get("signal_types"),
        "signal_type",
        limit=MAX_EVIDENCE_ITEMS,
    )
    paths = _build_count_list(
        evidence.get("request_paths"),
        "path",
        limit=MAX_EVIDENCE_ITEMS,
    )

    countries: list[dict[str, Any]] = []
    asns: list[dict[str, Any]] = []
    if allow_geo:
        countries = _query_top_countries(
            db,
            tenant_id=tenant_id,
            incident_id=incident.id,
            limit=MAX_GEO_ITEMS,
        )
        if allow_asn:
            asns = _query_top_asns(
                db,
                tenant_id=tenant_id,
                incident_id=incident.id,
                limit=MAX_GEO_ITEMS,
            )

    impact_payload = None
    if incident.impact_estimate_id:
        impact = (
            db.query(ImpactEstimate)
            .filter(
                ImpactEstimate.id == incident.impact_estimate_id,
                ImpactEstimate.tenant_id == tenant_id,
            )
            .first()
        )
        if impact:
            impact_payload = {
                "id": impact.id,
                "metric_key": impact.metric_key,
                "window_start": impact.window_start,
                "window_end": impact.window_end,
                "observed_rate": impact.observed_rate,
                "baseline_rate": impact.baseline_rate,
                "delta_rate": impact.delta_rate,
                "estimated_lost_conversions": impact.estimated_lost_conversions,
                "estimated_lost_revenue": impact.estimated_lost_revenue,
                "confidence": impact.confidence,
            }

    recovery_payload = None
    recovery = (
        db.query(IncidentRecovery)
        .filter(
            IncidentRecovery.incident_id == incident.id,
            IncidentRecovery.tenant_id == tenant_id,
        )
        .order_by(IncidentRecovery.measured_at.desc())
        .first()
    )
    if recovery:
        time_to_recover_hours = None
        if incident.last_seen_at:
            delta = recovery.measured_at - incident.last_seen_at
            time_to_recover_hours = max(delta.total_seconds() / 3600.0, 0.0)
        recovery_payload = {
            "id": recovery.id,
            "measured_at": recovery.measured_at,
            "window_start": recovery.window_start,
            "window_end": recovery.window_end,
            "post_conversion_rate": recovery.post_conversion_rate,
            "change_in_errors": recovery.change_in_errors,
            "change_in_threats": recovery.change_in_threats,
            "recovery_ratio": recovery.recovery_ratio,
            "confidence": recovery.confidence,
            "time_to_recover_hours": time_to_recover_hours,
        }

    report = {
        "incident": {
            "id": incident.id,
            "title": incident.title,
            "severity": incident.severity,
            "category": incident.category,
            "status": incident.status,
            "first_seen_at": incident.first_seen_at,
            "last_seen_at": incident.last_seen_at,
            "website_id": incident.website_id,
            "environment_id": incident.environment_id,
        },
        "evidence": {
            "counts": evidence_counts,
            "event_types": event_types,
            "signal_types": signal_types,
            "paths": paths,
            "countries": countries if allow_geo else [],
            "asns": asns if allow_asn else [],
        },
        "impact": impact_payload,
        "prescriptions": _build_prescription_items(
            db,
            tenant_id=tenant_id,
            incident_id=incident.id,
        ),
        "recovery": recovery_payload,
        "exported_at": datetime.utcnow(),
    }
    return report


def _format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _escape_csv(value: Any) -> str:
    text = _format_value(value)
    if not text:
        return ""
    if any(char in text for char in [",", "\"", "\n"]):
        return f"\"{text.replace('\"', '\"\"')}\""
    return text


def build_incident_report_csv(report: dict[str, Any]) -> str:
    incident = report.get("incident") or {}
    impact = report.get("impact") or {}
    recovery = report.get("recovery") or {}
    prescriptions = report.get("prescriptions") or []

    headers = [
        "section",
        "incident_id",
        "title",
        "severity",
        "category",
        "status",
        "first_seen_at",
        "last_seen_at",
        "impact_metric_key",
        "impact_window_start",
        "impact_window_end",
        "baseline_rate",
        "observed_rate",
        "estimated_lost_conversions",
        "estimated_lost_revenue",
        "impact_confidence",
        "recovery_measured_at",
        "recovery_window_start",
        "recovery_window_end",
        "post_conversion_rate",
        "recovery_ratio",
        "recovery_confidence",
        "time_to_recover_hours",
        "prescription_title",
        "prescription_status",
        "prescription_priority",
        "prescription_effort",
        "prescription_expected_effect",
        "prescription_notes",
    ]

    rows = []
    rows.append(
        [
            "incident",
            incident.get("id"),
            incident.get("title"),
            incident.get("severity"),
            incident.get("category"),
            incident.get("status"),
            incident.get("first_seen_at"),
            incident.get("last_seen_at"),
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
        ]
    )

    if impact:
        rows.append(
            [
                "impact",
                incident.get("id"),
                "",
                "",
                "",
                "",
                "",
                "",
                impact.get("metric_key"),
                impact.get("window_start"),
                impact.get("window_end"),
                impact.get("baseline_rate"),
                impact.get("observed_rate"),
                impact.get("estimated_lost_conversions"),
                impact.get("estimated_lost_revenue"),
                impact.get("confidence"),
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ]
        )

    if recovery:
        rows.append(
            [
                "recovery",
                incident.get("id"),
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                recovery.get("measured_at"),
                recovery.get("window_start"),
                recovery.get("window_end"),
                recovery.get("post_conversion_rate"),
                recovery.get("recovery_ratio"),
                recovery.get("confidence"),
                recovery.get("time_to_recover_hours"),
                "",
                "",
                "",
                "",
                "",
            ]
        )

    for item in prescriptions:
        rows.append(
            [
                "prescription",
                incident.get("id"),
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                item.get("title"),
                item.get("status"),
                item.get("priority"),
                item.get("effort"),
                item.get("expected_effect"),
                item.get("notes"),
            ]
        )

    lines = [",".join(headers)]
    for row in rows:
        lines.append(",".join(_escape_csv(value) for value in row))
    return "\n".join(lines)
