from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.behaviour_events import BehaviourEvent
from app.models.incidents import Incident
from app.models.revenue_leaks import RevenueLeakEstimate
from app.models.security_events import SecurityEvent
from app.models.trust_scoring import TrustSnapshot
from app.models.verification_runs import VerificationCheckRun


@dataclass
class Window:
    start: datetime
    end: datetime


def _window_for_incident(incident: Incident, *, before_hours: int, after_hours: int) -> tuple[Window, Window]:
    before_end = incident.first_seen_at or incident.created_at
    before_start = before_end - timedelta(hours=before_hours)
    after_start = incident.last_seen_at or incident.created_at
    after_end = min(datetime.utcnow(), after_start + timedelta(hours=after_hours))
    if after_end < after_start:
        after_end = after_start
    return Window(before_start, before_end), Window(after_start, after_end)


def _ratio_change(before: float, after: float) -> float | None:
    if before <= 0:
        return None
    return (after - before) / before


def _evaluate_drop(
    *,
    label: str,
    before: float,
    after: float,
    threshold: float,
    min_count: int = 5,
    evidence: dict | None = None,
    unit: str = "count",
) -> dict[str, Any]:
    if before < min_count and after < min_count:
        status = "inconclusive"
    elif before <= 0:
        status = "inconclusive"
    else:
        drop_ratio = (before - after) / before
        status = "passed" if drop_ratio >= threshold else "failed"
    return {
        "check_type": label,
        "label": label.replace("_", " ").title(),
        "status": status,
        "before": before,
        "after": after,
        "delta": _ratio_change(before, after),
        "threshold": threshold,
        "unit": unit,
        "evidence": evidence or {},
    }


def _evaluate_increase(
    *,
    label: str,
    before: float,
    after: float,
    threshold: float,
    min_count: int = 5,
    evidence: dict | None = None,
    unit: str = "count",
) -> dict[str, Any]:
    if before < min_count and after < min_count:
        status = "inconclusive"
    elif before <= 0:
        status = "inconclusive"
    else:
        increase_ratio = (after - before) / before
        status = "passed" if increase_ratio >= threshold else "failed"
    return {
        "check_type": label,
        "label": label.replace("_", " ").title(),
        "status": status,
        "before": before,
        "after": after,
        "delta": _ratio_change(before, after),
        "threshold": threshold,
        "unit": unit,
        "evidence": evidence or {},
    }


def _sum_security_events(
    db: Session,
    *,
    incident: Incident,
    window: Window,
    category_filter: str | None = None,
    event_type_keywords: list[str] | None = None,
) -> int:
    query = db.query(func.count(SecurityEvent.id)).filter(
        SecurityEvent.tenant_id == incident.tenant_id,
        SecurityEvent.created_at >= window.start,
        SecurityEvent.created_at <= window.end,
    )
    if incident.website_id is not None:
        query = query.filter(SecurityEvent.website_id == incident.website_id)
    if incident.environment_id is not None:
        query = query.filter(SecurityEvent.environment_id == incident.environment_id)
    if category_filter:
        query = query.filter(SecurityEvent.category == category_filter)
    if event_type_keywords:
        conditions = [
            func.lower(SecurityEvent.event_type).like(f"%{keyword.lower()}%")
            for keyword in event_type_keywords
        ]
        if conditions:
            query = query.filter(or_(*conditions))
    return int(query.scalar() or 0)


def _sum_behaviour_events(
    db: Session,
    *,
    incident: Incident,
    window: Window,
    event_types: list[str],
) -> int:
    query = db.query(func.count(BehaviourEvent.id)).filter(
        BehaviourEvent.tenant_id == incident.tenant_id,
        BehaviourEvent.ingested_at >= window.start,
        BehaviourEvent.ingested_at <= window.end,
        BehaviourEvent.event_type.in_(event_types),
    )
    if incident.website_id is not None:
        query = query.filter(BehaviourEvent.website_id == incident.website_id)
    if incident.environment_id is not None:
        query = query.filter(BehaviourEvent.environment_id == incident.environment_id)
    return int(query.scalar() or 0)


def _avg_trust_score(
    db: Session,
    *,
    incident: Incident,
    window: Window,
) -> float | None:
    query = db.query(func.avg(TrustSnapshot.trust_score)).filter(
        TrustSnapshot.tenant_id == incident.tenant_id,
        TrustSnapshot.bucket_start >= window.start,
        TrustSnapshot.bucket_start <= window.end,
    )
    if incident.website_id is not None:
        query = query.filter(TrustSnapshot.website_id == incident.website_id)
    if incident.environment_id is not None:
        query = query.filter(TrustSnapshot.environment_id == incident.environment_id)
    value = query.scalar()
    return float(value) if value is not None else None


def _sum_revenue_leak(
    db: Session,
    *,
    incident: Incident,
    window: Window,
) -> float:
    query = db.query(func.sum(RevenueLeakEstimate.estimated_lost_revenue)).filter(
        RevenueLeakEstimate.tenant_id == incident.tenant_id,
        RevenueLeakEstimate.bucket_start >= window.start,
        RevenueLeakEstimate.bucket_start <= window.end,
    )
    if incident.website_id is not None:
        query = query.filter(RevenueLeakEstimate.website_id == incident.website_id)
    if incident.environment_id is not None:
        query = query.filter(RevenueLeakEstimate.environment_id == incident.environment_id)
    value = query.scalar()
    return float(value) if value is not None else 0.0


def evaluate_verification(
    db: Session,
    *,
    incident: Incident,
    before_hours: int = 24,
    after_hours: int = 6,
) -> VerificationCheckRun:
    before_window, after_window = _window_for_incident(
        incident,
        before_hours=before_hours,
        after_hours=after_hours,
    )

    checks: list[dict[str, Any]] = []

    threat_before = _sum_security_events(db, incident=incident, window=before_window)
    threat_after = _sum_security_events(db, incident=incident, window=after_window)
    checks.append(
        _evaluate_drop(
            label="threat_volume_reduction",
            before=threat_before,
            after=threat_after,
            threshold=0.3,
            evidence={"window_before": [before_window.start.isoformat(), before_window.end.isoformat()],
                      "window_after": [after_window.start.isoformat(), after_window.end.isoformat()]},
        )
    )

    login_before = _sum_security_events(
        db,
        incident=incident,
        window=before_window,
        category_filter="login",
        event_type_keywords=["login", "credential", "brute"],
    )
    login_after = _sum_security_events(
        db,
        incident=incident,
        window=after_window,
        category_filter="login",
        event_type_keywords=["login", "credential", "brute"],
    )
    checks.append(
        _evaluate_drop(
            label="login_failures_reduction",
            before=login_before,
            after=login_after,
            threshold=0.3,
        )
    )

    js_before = _sum_behaviour_events(
        db,
        incident=incident,
        window=before_window,
        event_types=["js_error", "error"],
    )
    js_after = _sum_behaviour_events(
        db,
        incident=incident,
        window=after_window,
        event_types=["js_error", "error"],
    )
    checks.append(
        _evaluate_drop(
            label="js_error_reduction",
            before=js_before,
            after=js_after,
            threshold=0.25,
        )
    )

    form_before = _sum_behaviour_events(
        db,
        incident=incident,
        window=before_window,
        event_types=["form_submit"],
    )
    form_after = _sum_behaviour_events(
        db,
        incident=incident,
        window=after_window,
        event_types=["form_submit"],
    )
    checks.append(
        _evaluate_increase(
            label="form_submit_success_improvement",
            before=form_before,
            after=form_after,
            threshold=0.05,
        )
    )

    trust_before = _avg_trust_score(db, incident=incident, window=before_window)
    trust_after = _avg_trust_score(db, incident=incident, window=after_window)
    if trust_before is None or trust_after is None:
        checks.append(
            {
                "check_type": "trust_score_recovery",
                "label": "Trust Score Recovery",
                "status": "inconclusive",
                "before": trust_before,
                "after": trust_after,
                "delta": _ratio_change(trust_before or 0.0, trust_after or 0.0),
                "threshold": 5,
                "unit": "score",
                "evidence": {},
            }
        )
    else:
        status = "passed" if trust_after >= max(80, trust_before + 5) else "failed"
        checks.append(
            {
                "check_type": "trust_score_recovery",
                "label": "Trust Score Recovery",
                "status": status,
                "before": trust_before,
                "after": trust_after,
                "delta": trust_after - trust_before,
                "threshold": 5,
                "unit": "score",
                "evidence": {},
            }
        )

    leak_before = _sum_revenue_leak(db, incident=incident, window=before_window)
    leak_after = _sum_revenue_leak(db, incident=incident, window=after_window)
    checks.append(
        _evaluate_drop(
            label="revenue_leak_reduction",
            before=leak_before,
            after=leak_after,
            threshold=0.3,
            unit="currency",
        )
    )

    status = "inconclusive"
    if any(check["status"] == "failed" for check in checks):
        status = "failed"
    elif any(check["status"] == "passed" for check in checks):
        status = "passed"

    run = VerificationCheckRun(
        tenant_id=incident.tenant_id,
        website_id=incident.website_id,
        environment_id=incident.environment_id,
        incident_id=incident.id,
        status=status,
        checks_json=checks,
        notes=None,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run
