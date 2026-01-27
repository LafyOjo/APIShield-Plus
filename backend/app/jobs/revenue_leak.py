from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.revenue_impact import compute_baseline, compute_impact
from app.models.behaviour_events import BehaviourEvent
from app.models.revenue_impact import ConversionMetric
from app.models.incidents import Incident
from app.models.revenue_leaks import RevenueLeakEstimate
from app.models.tenant_settings import TenantSettings
from app.models.trust_scoring import TrustSnapshot


def _truncate_hour(value: datetime) -> datetime:
    return value.replace(minute=0, second=0, microsecond=0)


def _distinct_sessions(
    db: Session,
    *,
    tenant_id: int,
    website_id: int,
    environment_id: int,
    from_ts: datetime,
    to_ts: datetime,
    event_type: str,
    path: str | None,
) -> int:
    query = (
        db.query(func.count(func.distinct(BehaviourEvent.session_id)))
        .filter(
            BehaviourEvent.tenant_id == tenant_id,
            BehaviourEvent.website_id == website_id,
            BehaviourEvent.environment_id == environment_id,
            BehaviourEvent.session_id.isnot(None),
            BehaviourEvent.event_type == event_type,
            BehaviourEvent.event_ts >= from_ts,
            BehaviourEvent.event_ts < to_ts,
        )
    )
    if path:
        query = query.filter(BehaviourEvent.path == path)
    return int(query.scalar() or 0)


def _window_conversion_stats(
    db: Session,
    *,
    tenant_id: int,
    website_id: int,
    environment_id: int,
    from_ts: datetime,
    to_ts: datetime,
    path: str | None,
) -> dict[str, float | int]:
    sessions = _distinct_sessions(
        db,
        tenant_id=tenant_id,
        website_id=website_id,
        environment_id=environment_id,
        from_ts=from_ts,
        to_ts=to_ts,
        event_type="page_view",
        path=path,
    )
    conversions = _distinct_sessions(
        db,
        tenant_id=tenant_id,
        website_id=website_id,
        environment_id=environment_id,
        from_ts=from_ts,
        to_ts=to_ts,
        event_type="form_submit",
        path=path,
    )
    rate = conversions / sessions if sessions else 0.0
    return {
        "sessions": sessions,
        "conversions": conversions,
        "conversion_rate": rate,
    }


def _baseline_from_metrics(
    db: Session,
    *,
    tenant_id: int,
    website_id: int,
    environment_id: int,
    metric_key: str,
    baseline_start: datetime,
    baseline_end: datetime,
) -> tuple[float | None, float | None, list[ConversionMetric]]:
    metrics = (
        db.query(ConversionMetric)
        .filter(
            ConversionMetric.tenant_id == tenant_id,
            ConversionMetric.website_id == website_id,
            ConversionMetric.environment_id == environment_id,
            ConversionMetric.metric_key == metric_key,
            ConversionMetric.window_end >= baseline_start,
            ConversionMetric.window_end <= baseline_end,
        )
        .order_by(ConversionMetric.window_end.desc())
        .all()
    )
    if not metrics:
        return None, None, []
    baseline = compute_baseline(metrics, window_days=max(1, int((baseline_end - baseline_start).days)))
    revenue_values = [row.revenue_per_conversion for row in metrics if row.revenue_per_conversion is not None]
    revenue_per_conversion = revenue_values[0] if revenue_values else None
    return baseline, revenue_per_conversion, metrics


def _incident_overlap(
    db: Session,
    *,
    tenant_id: int,
    website_id: int,
    environment_id: int,
    bucket_start: datetime,
    bucket_end: datetime,
    path: str | None,
) -> list[int]:
    incidents = (
        db.query(Incident)
        .filter(
            Incident.tenant_id == tenant_id,
            Incident.website_id == website_id,
            Incident.environment_id == environment_id,
            Incident.first_seen_at <= bucket_end,
            Incident.last_seen_at >= bucket_start,
        )
        .all()
    )
    if not incidents:
        return []
    if not path:
        return [incident.id for incident in incidents]
    matches: list[int] = []
    for incident in incidents:
        evidence = incident.evidence_json if isinstance(incident.evidence_json, dict) else {}
        paths = evidence.get("request_paths") if isinstance(evidence, dict) else None
        if isinstance(paths, dict) and path in paths:
            matches.append(incident.id)
        elif incident.summary and path in incident.summary:
            matches.append(incident.id)
    return matches


def _confidence_from_trust(trust_score: int | None, factor_count: int) -> float:
    score = 0.35
    if trust_score is not None:
        if trust_score <= 50:
            score += 0.3
        elif trust_score <= 70:
            score += 0.15
    if factor_count:
        score += min(0.2, factor_count * 0.05)
    return min(0.95, score)


def run_revenue_leak_job(
    db: Session,
    *,
    lookback_hours: int = 24,
    recompute_hours: int = 2,
    baseline_days: int = 14,
) -> int:
    now = datetime.utcnow()
    window_start = now - timedelta(hours=max(1, int(lookback_hours)))
    current_bucket = _truncate_hour(now)
    recompute_cutoff = current_bucket - timedelta(hours=max(0, int(recompute_hours) - 1))

    snapshots = (
        db.query(TrustSnapshot)
        .filter(TrustSnapshot.bucket_start >= window_start)
        .order_by(TrustSnapshot.bucket_start.asc())
        .all()
    )
    if not snapshots:
        return 0

    existing_keys = {
        (row.tenant_id, row.website_id, row.environment_id, row.path, row.bucket_start)
        for row in db.query(RevenueLeakEstimate)
        .filter(RevenueLeakEstimate.bucket_start >= window_start)
        .all()
    }

    grouped: dict[tuple[int, int, int, str | None, datetime], TrustSnapshot] = {}
    for snapshot in snapshots:
        key = (
            snapshot.tenant_id,
            snapshot.website_id,
            snapshot.environment_id,
            snapshot.path,
            snapshot.bucket_start,
        )
        grouped[key] = snapshot

    updated = 0
    for key, snapshot in grouped.items():
        tenant_id, website_id, environment_id, path, bucket_start = key
        if bucket_start < recompute_cutoff and key in existing_keys:
            continue

        bucket_end = bucket_start + timedelta(hours=1)
        stats = _window_conversion_stats(
            db,
            tenant_id=tenant_id,
            website_id=website_id,
            environment_id=environment_id,
            from_ts=bucket_start,
            to_ts=bucket_end,
            path=path,
        )
        sessions = int(stats["sessions"])
        conversions = int(stats["conversions"])
        if sessions == 0:
            continue

        baseline_start = bucket_start - timedelta(days=max(1, int(baseline_days)))
        metric_key = f"funnel:{path or 'site'}"
        baseline_rate, revenue_per_conversion, metrics = _baseline_from_metrics(
            db,
            tenant_id=tenant_id,
            website_id=website_id,
            environment_id=environment_id,
            metric_key=metric_key,
            baseline_start=baseline_start,
            baseline_end=bucket_start,
        )
        baseline_source = "conversion_metrics"
        if baseline_rate is None:
            baseline_stats = _window_conversion_stats(
                db,
                tenant_id=tenant_id,
                website_id=website_id,
                environment_id=environment_id,
                from_ts=baseline_start,
                to_ts=bucket_start,
                path=path,
            )
            baseline_rate = float(baseline_stats["conversion_rate"])
            baseline_source = "behaviour_events"

        settings = (
            db.query(TenantSettings)
            .filter(TenantSettings.tenant_id == tenant_id)
            .first()
        )
        if revenue_per_conversion is None and settings is not None:
            revenue_per_conversion = settings.default_revenue_per_conversion

        impact = compute_impact(
            observed_rate=float(stats["conversion_rate"]),
            baseline_rate=float(baseline_rate or 0.0),
            sessions=sessions,
            revenue_per_conversion=revenue_per_conversion,
        )

        expected_conversions = float(baseline_rate or 0.0) * sessions
        lost_conversions = float(impact["estimated_lost_conversions"] or 0.0)
        lost_revenue = impact["estimated_lost_revenue"]
        confidence = _confidence_from_trust(snapshot.trust_score, snapshot.factor_count)
        if lost_conversions > 0:
            confidence = min(0.95, confidence + 0.1)

        incident_ids = _incident_overlap(
            db,
            tenant_id=tenant_id,
            website_id=website_id,
            environment_id=environment_id,
            bucket_start=bucket_start,
            bucket_end=bucket_end,
            path=path,
        )

        explanation = {
            "metric_key": metric_key,
            "baseline_source": baseline_source,
            "baseline_window_days": baseline_days,
            "metric_rows": len(metrics),
            "sessions": sessions,
            "observed_conversions": conversions,
            "baseline_rate": float(baseline_rate or 0.0),
            "observed_rate": float(stats["conversion_rate"]),
            "trust_score": snapshot.trust_score,
            "trust_factor_count": snapshot.factor_count,
            "incident_ids": incident_ids,
        }

        db.query(RevenueLeakEstimate).filter(
            RevenueLeakEstimate.tenant_id == tenant_id,
            RevenueLeakEstimate.website_id == website_id,
            RevenueLeakEstimate.environment_id == environment_id,
            RevenueLeakEstimate.path == path,
            RevenueLeakEstimate.bucket_start == bucket_start,
        ).delete()

        db.add(
            RevenueLeakEstimate(
                tenant_id=tenant_id,
                website_id=website_id,
                environment_id=environment_id,
                bucket_start=bucket_start,
                path=path,
                baseline_conversion_rate=baseline_rate,
                observed_conversion_rate=float(stats["conversion_rate"]),
                sessions_in_bucket=sessions,
                expected_conversions=expected_conversions,
                observed_conversions=conversions,
                lost_conversions=lost_conversions,
                revenue_per_conversion=revenue_per_conversion,
                estimated_lost_revenue=lost_revenue,
                linked_trust_score=snapshot.trust_score,
                confidence=confidence,
                explanation_json=explanation,
                created_at=now,
            )
        )

        updated += 1

    if updated:
        db.commit()
    return updated
