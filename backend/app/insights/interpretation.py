from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.revenue_impact import compute_baseline, compute_impact
from app.models.behaviour_events import BehaviourEvent
from app.models.incidents import Incident
from app.models.revenue_impact import ConversionMetric, ImpactEstimate
from app.models.tenant_settings import TenantSettings


DEFAULT_BASELINE_DAYS = 14
EXTENDED_BASELINE_DAYS = 28
MIN_SESSIONS = 20
MIN_BASELINE_SESSIONS = 50
MAX_PATHS = 5

HIGH_IMPACT_PATHS = (
    "/checkout",
    "/payment",
    "/cart",
    "/login",
    "/signup",
    "/register",
)

CATEGORY_FALLBACK_PATHS = {
    "login": ["/login", "/auth"],
    "threat": ["/checkout", "/payment"],
    "integrity": ["/checkout", "/payment"],
    "bot": ["/login"],
    "mixed": ["/checkout"],
    "anomaly": ["/checkout"],
}

SEVERITY_WEIGHTS = {
    "low": 0.05,
    "medium": 0.1,
    "high": 0.15,
    "critical": 0.2,
}


def _normalize_ts(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _normalize_path(value: str | None) -> str | None:
    if not value or not isinstance(value, str):
        return None
    path = value.strip()
    if not path.startswith("/"):
        return None
    return path


def _extract_paths(incident: Incident) -> list[str]:
    paths: list[str] = []
    evidence = incident.evidence_json if isinstance(incident.evidence_json, dict) else {}
    path_map = evidence.get("request_paths") if isinstance(evidence, dict) else None
    if isinstance(path_map, dict):
        sorted_paths = sorted(path_map.items(), key=lambda item: _safe_int(item[1]), reverse=True)
        for raw_path, _count in sorted_paths:
            normalized = _normalize_path(raw_path)
            if normalized and normalized not in paths:
                paths.append(normalized)
            if len(paths) >= MAX_PATHS:
                break
    if not paths:
        fallback = CATEGORY_FALLBACK_PATHS.get((incident.category or "").lower(), [])
        for raw_path in fallback:
            normalized = _normalize_path(raw_path)
            if normalized and normalized not in paths:
                paths.append(normalized)
    return paths


def _infer_metric_key(incident: Incident, paths: list[str]) -> str:
    for path in paths:
        lowered = path.lower()
        if "checkout" in lowered or "payment" in lowered or "cart" in lowered:
            return "checkout_conversion"
        if "signup" in lowered or "register" in lowered:
            return "signup_conversion"
        if "login" in lowered or "auth" in lowered:
            return "login_conversion"
    category = (incident.category or "").lower()
    if category == "login":
        return "login_conversion"
    if category in {"threat", "integrity"}:
        return "checkout_conversion"
    return "conversion_rate"


def _distinct_sessions(
    db: Session,
    *,
    tenant_id: int,
    website_id: int | None,
    environment_id: int | None,
    from_ts: datetime,
    to_ts: datetime,
    event_type: str,
    paths: list[str],
) -> int:
    query = (
        db.query(func.count(func.distinct(BehaviourEvent.session_id)))
        .filter(
            BehaviourEvent.tenant_id == tenant_id,
            BehaviourEvent.session_id.isnot(None),
            BehaviourEvent.event_type == event_type,
            BehaviourEvent.event_ts >= from_ts,
            BehaviourEvent.event_ts <= to_ts,
        )
    )
    if website_id is not None:
        query = query.filter(BehaviourEvent.website_id == website_id)
    if environment_id is not None:
        query = query.filter(BehaviourEvent.environment_id == environment_id)
    if paths:
        query = query.filter(BehaviourEvent.path.in_(paths))
    return int(query.scalar() or 0)


def _window_stats(
    db: Session,
    *,
    tenant_id: int,
    website_id: int | None,
    environment_id: int | None,
    from_ts: datetime,
    to_ts: datetime,
    paths: list[str],
) -> dict[str, float | int]:
    view_sessions = _distinct_sessions(
        db,
        tenant_id=tenant_id,
        website_id=website_id,
        environment_id=environment_id,
        from_ts=from_ts,
        to_ts=to_ts,
        event_type="page_view",
        paths=paths,
    )
    submit_sessions = _distinct_sessions(
        db,
        tenant_id=tenant_id,
        website_id=website_id,
        environment_id=environment_id,
        from_ts=from_ts,
        to_ts=to_ts,
        event_type="form_submit",
        paths=paths,
    )
    error_sessions = _distinct_sessions(
        db,
        tenant_id=tenant_id,
        website_id=website_id,
        environment_id=environment_id,
        from_ts=from_ts,
        to_ts=to_ts,
        event_type="error",
        paths=paths,
    )
    conversion_rate = submit_sessions / view_sessions if view_sessions else 0.0
    error_rate = error_sessions / view_sessions if view_sessions else 0.0
    return {
        "view_sessions": view_sessions,
        "submit_sessions": submit_sessions,
        "error_sessions": error_sessions,
        "conversion_rate": conversion_rate,
        "submit_rate": conversion_rate,
        "error_rate": error_rate,
    }


def _baseline_rate_from_metrics(
    db: Session,
    *,
    incident: Incident,
    metric_key: str,
    baseline_start: datetime,
    incident_start: datetime,
    baseline_days: int,
) -> tuple[float | None, list[ConversionMetric]]:
    query = (
        db.query(ConversionMetric)
        .filter(
            ConversionMetric.tenant_id == incident.tenant_id,
            ConversionMetric.metric_key == metric_key,
            ConversionMetric.window_end >= baseline_start,
            ConversionMetric.window_end <= incident_start,
        )
    )
    if incident.website_id is not None:
        query = query.filter(ConversionMetric.website_id == incident.website_id)
    if incident.environment_id is not None:
        query = query.filter(ConversionMetric.environment_id == incident.environment_id)
    metrics = query.all()
    if not metrics:
        return None, []
    baseline = compute_baseline(metrics, window_days=baseline_days, now=incident_start)
    return baseline, metrics


def _signal_rate_per_minute(incident: Incident, duration_minutes: float) -> float:
    evidence = incident.evidence_json if isinstance(incident.evidence_json, dict) else {}
    counts = evidence.get("counts") if isinstance(evidence, dict) else None
    if not isinstance(counts, dict) or duration_minutes <= 0:
        return 0.0
    total = sum(_safe_int(value) for value in counts.values())
    return total / max(duration_minutes, 1.0)


def _score_confidence(
    incident: Incident,
    *,
    paths: list[str],
    observed_stats: dict[str, float | int],
    baseline_stats: dict[str, float | int],
    observed_rate: float,
    baseline_rate: float,
    duration_minutes: float,
) -> tuple[float, dict[str, Any]]:
    factors: dict[str, Any] = {}
    score = 0.05

    path_overlap = any(path.lower().startswith(HIGH_IMPACT_PATHS) for path in paths)
    if path_overlap:
        score += 0.2
    factors["path_overlap"] = path_overlap

    severity = (incident.severity or "").lower()
    severity_weight = SEVERITY_WEIGHTS.get(severity, 0.05)
    score += severity_weight
    factors["severity_weight"] = severity_weight

    category = (incident.category or "").lower()
    category_weight = 0.05 if category in {"login", "threat", "integrity"} else 0.0
    score += category_weight
    factors["category_weight"] = category_weight

    observed_error = float(observed_stats.get("error_rate") or 0.0)
    baseline_error = float(baseline_stats.get("error_rate") or 0.0)
    error_spike = False
    if baseline_error > 0:
        error_spike = observed_error >= baseline_error * 1.5 and (observed_error - baseline_error) >= 0.05
    if error_spike:
        score += 0.15
    factors["error_spike"] = error_spike

    observed_submit = float(observed_stats.get("submit_rate") or 0.0)
    baseline_submit = float(baseline_stats.get("submit_rate") or 0.0)
    submit_drop = False
    if baseline_submit > 0:
        submit_drop = (baseline_submit - observed_submit) >= 0.05
    if submit_drop:
        score += 0.15
    factors["submit_drop"] = submit_drop

    conversion_drop = False
    if baseline_rate > 0:
        conversion_drop = (baseline_rate - observed_rate) >= 0.05
    if conversion_drop:
        score += 0.2
    factors["conversion_drop"] = conversion_drop

    signal_rate = _signal_rate_per_minute(incident, duration_minutes)
    signal_spike = signal_rate >= 2.0
    if signal_spike:
        score += 0.05
    factors["signal_rate_per_minute"] = round(signal_rate, 4)
    factors["signal_spike"] = signal_spike

    score = min(score, 0.85)
    return score, factors


def _impact_summary(impact: ImpactEstimate) -> str:
    observed_pct = impact.observed_rate * 100.0
    baseline_pct = impact.baseline_rate * 100.0
    lost = impact.estimated_lost_conversions
    return (
        f"Observed conversion {observed_pct:.1f}% vs baseline {baseline_pct:.1f}% "
        f"during incident window. Estimated lost conversions {lost:.1f}."
    )


def interpret_incident(
    db: Session,
    incident_id: int,
    *,
    baseline_days: int = DEFAULT_BASELINE_DAYS,
) -> ImpactEstimate | None:
    incident = (
        db.query(Incident)
        .filter(Incident.id == incident_id)
        .first()
    )
    if not incident:
        return None
    return interpret_incident_record(db, incident=incident, baseline_days=baseline_days)


def interpret_incident_record(
    db: Session,
    *,
    incident: Incident,
    baseline_days: int = DEFAULT_BASELINE_DAYS,
) -> ImpactEstimate | None:
    start = _normalize_ts(incident.first_seen_at)
    end = _normalize_ts(incident.last_seen_at)
    if not start or not end:
        return None
    if end < start:
        start, end = end, start

    duration_minutes = max((end - start).total_seconds() / 60.0, 1.0)
    paths = _extract_paths(incident)
    metric_key = _infer_metric_key(incident, paths)

    observed_stats = _window_stats(
        db,
        tenant_id=incident.tenant_id,
        website_id=incident.website_id,
        environment_id=incident.environment_id,
        from_ts=start,
        to_ts=end,
        paths=paths,
    )
    observed_sessions = int(observed_stats.get("view_sessions") or 0)
    if observed_sessions < MIN_SESSIONS:
        return None

    baseline_start = start - timedelta(days=baseline_days)
    baseline_stats = _window_stats(
        db,
        tenant_id=incident.tenant_id,
        website_id=incident.website_id,
        environment_id=incident.environment_id,
        from_ts=baseline_start,
        to_ts=start,
        paths=paths,
    )
    baseline_sessions = int(baseline_stats.get("view_sessions") or 0)
    if baseline_sessions < MIN_BASELINE_SESSIONS and baseline_days < EXTENDED_BASELINE_DAYS:
        baseline_days = EXTENDED_BASELINE_DAYS
        baseline_start = start - timedelta(days=baseline_days)
        baseline_stats = _window_stats(
            db,
            tenant_id=incident.tenant_id,
            website_id=incident.website_id,
            environment_id=incident.environment_id,
            from_ts=baseline_start,
            to_ts=start,
            paths=paths,
        )
        baseline_sessions = int(baseline_stats.get("view_sessions") or 0)

    if baseline_sessions < MIN_BASELINE_SESSIONS:
        return None

    baseline_rate = None
    baseline_source = "behaviour_events"
    baseline_from_metrics, metrics = _baseline_rate_from_metrics(
        db,
        incident=incident,
        metric_key=metric_key,
        baseline_start=baseline_start,
        incident_start=start,
        baseline_days=baseline_days,
    )
    if baseline_from_metrics is not None:
        baseline_rate = baseline_from_metrics
        baseline_source = "conversion_metrics"
    else:
        baseline_rate = float(baseline_stats.get("conversion_rate") or 0.0)

    observed_rate = float(observed_stats.get("conversion_rate") or 0.0)
    settings = (
        db.query(TenantSettings)
        .filter(TenantSettings.tenant_id == incident.tenant_id)
        .first()
    )
    revenue_per_conversion = settings.default_revenue_per_conversion if settings else None
    impact_values = compute_impact(
        observed_rate=observed_rate,
        baseline_rate=baseline_rate,
        sessions=observed_sessions,
        revenue_per_conversion=revenue_per_conversion,
    )

    confidence, factors = _score_confidence(
        incident,
        paths=paths,
        observed_stats=observed_stats,
        baseline_stats=baseline_stats,
        observed_rate=float(impact_values["observed_rate"] or 0.0),
        baseline_rate=float(impact_values["baseline_rate"] or 0.0),
        duration_minutes=duration_minutes,
    )

    explanation = {
        "metric_key": metric_key,
        "window": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "duration_minutes": round(duration_minutes, 2),
        },
        "paths": paths,
        "observed": {
            "sessions": observed_sessions,
            "conversion_rate": impact_values["observed_rate"],
            "error_rate": observed_stats.get("error_rate"),
            "submit_rate": observed_stats.get("submit_rate"),
        },
        "baseline": {
            "sessions": baseline_sessions,
            "conversion_rate": impact_values["baseline_rate"],
            "error_rate": baseline_stats.get("error_rate"),
            "submit_rate": baseline_stats.get("submit_rate"),
            "source": baseline_source,
            "window_days": baseline_days,
            "metric_rows": len(metrics),
        },
        "signals": {
            "category": incident.category,
            "severity": incident.severity,
            "counts": (incident.evidence_json or {}).get("counts") if isinstance(incident.evidence_json, dict) else None,
        },
        "confidence_factors": factors,
    }

    impact = None
    if incident.impact_estimate_id:
        impact = (
            db.query(ImpactEstimate)
            .filter(
                ImpactEstimate.id == incident.impact_estimate_id,
                ImpactEstimate.tenant_id == incident.tenant_id,
            )
            .first()
        )
    if impact is None:
        impact = ImpactEstimate(
            tenant_id=incident.tenant_id,
            website_id=incident.website_id,
            environment_id=incident.environment_id,
            metric_key=metric_key,
            incident_id=str(incident.id),
            window_start=start,
            window_end=end,
            observed_rate=float(impact_values["observed_rate"] or 0.0),
            baseline_rate=float(impact_values["baseline_rate"] or 0.0),
            delta_rate=float(impact_values["delta_rate"] or 0.0),
            estimated_lost_conversions=float(impact_values["estimated_lost_conversions"] or 0.0),
            estimated_lost_revenue=impact_values["estimated_lost_revenue"],
            confidence=confidence,
            explanation_json=explanation,
        )
        db.add(impact)
        db.flush()
    else:
        impact.metric_key = metric_key
        impact.window_start = start
        impact.window_end = end
        impact.observed_rate = float(impact_values["observed_rate"] or 0.0)
        impact.baseline_rate = float(impact_values["baseline_rate"] or 0.0)
        impact.delta_rate = float(impact_values["delta_rate"] or 0.0)
        impact.estimated_lost_conversions = float(impact_values["estimated_lost_conversions"] or 0.0)
        impact.estimated_lost_revenue = impact_values["estimated_lost_revenue"]
        impact.confidence = confidence
        impact.explanation_json = explanation

    incident.impact_estimate_id = impact.id
    incident.summary = _impact_summary(impact)
    return impact
