from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models.anomaly_signals import AnomalySignalEvent
from app.models.behaviour_events import BehaviourEvent
from app.models.security_events import SecurityEvent
from app.models.trust_scoring import TrustFactorAgg, TrustSnapshot
from app.trust.framework import FactorSeverity, FactorType, RiskFactor, compute_trust_score


@dataclass
class _FactorAggregate:
    count: int = 0
    last_seen: datetime | None = None
    event_types: dict[str, int] = field(default_factory=dict)
    ip_hashes: dict[str, int] = field(default_factory=dict)

    def record(self, observed_at: datetime, *, event_type: str | None = None, ip_hash: str | None = None) -> None:
        self.count += 1
        if self.last_seen is None or observed_at > self.last_seen:
            self.last_seen = observed_at
        if event_type:
            self.event_types[event_type] = self.event_types.get(event_type, 0) + 1
        if ip_hash:
            self.ip_hashes[ip_hash] = self.ip_hashes.get(ip_hash, 0) + 1

    def evidence(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"count": self.count}
        if self.event_types:
            payload["top_event_types"] = _top_pairs(self.event_types)
        if self.ip_hashes:
            payload["top_ip_hashes"] = _top_pairs(self.ip_hashes)
        return payload


GROUP_KEY = tuple[int, int, int, str | None, datetime]


def _top_pairs(values: dict[str, int], limit: int = 3) -> list[dict[str, Any]]:
    return [
        {"key": key, "count": count}
        for key, count in sorted(values.items(), key=lambda item: item[1], reverse=True)[:limit]
    ]


def _truncate_hour(value: datetime) -> datetime:
    return value.replace(minute=0, second=0, microsecond=0)


def _severity_for_count(count: int) -> FactorSeverity | None:
    if count >= 50:
        return FactorSeverity.CRITICAL
    if count >= 20:
        return FactorSeverity.HIGH
    if count >= 5:
        return FactorSeverity.MEDIUM
    if count >= 2:
        return FactorSeverity.LOW
    return None


def _map_security_event(event: SecurityEvent) -> FactorType | None:
    event_type = (event.event_type or "").lower()
    category = (event.category or "").lower()

    if "credential_stuff" in event_type:
        return FactorType.CREDENTIAL_STUFFING_DETECTED
    if "login" in event_type and "fail" in event_type:
        return FactorType.LOGIN_FAIL_SPIKE
    if "csp" in event_type:
        return FactorType.CSP_VIOLATION_SPIKE
    if "script" in event_type or "injection" in event_type:
        return FactorType.SCRIPT_INJECTION_SIGNAL
    if "datacenter" in event_type or "bot" in event_type or bool(event.is_datacenter):
        return FactorType.DATACENTER_ASN_SURGE
    if "geo" in event_type and "novel" in event_type:
        return FactorType.GEO_NOVELTY_LOGIN
    if category == "integrity" and "violation" in event_type:
        return FactorType.CSP_VIOLATION_SPIKE
    return None


def _is_form_failure(meta: dict[str, Any] | None) -> bool:
    if not meta or not isinstance(meta, dict):
        return False
    if meta.get("success") is False:
        return True
    status = meta.get("status")
    if isinstance(status, str) and status.lower() in {"fail", "failed", "error"}:
        return True
    return False


def _map_behaviour_event(event: BehaviourEvent) -> FactorType | None:
    event_type = (event.event_type or "").lower()
    if event_type == "error":
        return FactorType.JS_ERROR_SPIKE
    if event_type == "form_submit" and _is_form_failure(event.meta):
        return FactorType.FORM_SUBMIT_FAIL_SPIKE
    return None


def _map_anomaly_signal(signal_type: str) -> FactorType | None:
    normalized = (signal_type or "").lower()
    for factor in FactorType:
        if normalized == factor.value:
            return factor
    if "conversion" in normalized and "drop" in normalized:
        return FactorType.CONVERSION_DROP_OVERLAP
    if "js_error" in normalized:
        return FactorType.JS_ERROR_SPIKE
    return None


def _record_factor(
    store: dict[GROUP_KEY, dict[FactorType, _FactorAggregate]],
    *,
    tenant_id: int,
    website_id: int,
    environment_id: int,
    path: str | None,
    bucket_start: datetime,
    factor_type: FactorType,
    observed_at: datetime,
    event_type: str | None = None,
    ip_hash: str | None = None,
) -> None:
    key: GROUP_KEY = (tenant_id, website_id, environment_id, path, bucket_start)
    factor_map = store.setdefault(key, {})
    aggregate = factor_map.setdefault(factor_type, _FactorAggregate())
    aggregate.record(observed_at, event_type=event_type, ip_hash=ip_hash)


def run_trust_scoring(
    db: Session,
    *,
    lookback_hours: int = 24,
    recompute_hours: int = 2,
) -> int:
    now = datetime.utcnow()
    window_start = now - timedelta(hours=max(1, int(lookback_hours)))
    current_bucket = _truncate_hour(now)
    recompute_cutoff = current_bucket - timedelta(hours=max(0, int(recompute_hours) - 1))

    existing_snapshot_keys = {
        (row.tenant_id, row.website_id, row.environment_id, row.path, row.bucket_start)
        for row in db.query(TrustSnapshot)
        .filter(TrustSnapshot.bucket_start >= window_start)
        .all()
    }

    factors: dict[GROUP_KEY, dict[FactorType, _FactorAggregate]] = defaultdict(dict)

    security_events = (
        db.query(SecurityEvent)
        .filter(SecurityEvent.created_at >= window_start)
        .all()
    )
    for event in security_events:
        if not event.website_id or not event.environment_id:
            continue
        factor_type = _map_security_event(event)
        if not factor_type:
            continue
        bucket_start = _truncate_hour(event.created_at or now)
        _record_factor(
            factors,
            tenant_id=event.tenant_id,
            website_id=event.website_id,
            environment_id=event.environment_id,
            path=event.request_path,
            bucket_start=bucket_start,
            factor_type=factor_type,
            observed_at=event.created_at or now,
            event_type=event.event_type,
            ip_hash=event.ip_hash,
        )

    behaviour_events = (
        db.query(BehaviourEvent)
        .filter(BehaviourEvent.ingested_at >= window_start)
        .all()
    )
    for event in behaviour_events:
        factor_type = _map_behaviour_event(event)
        if not factor_type:
            continue
        bucket_start = _truncate_hour(event.ingested_at or now)
        _record_factor(
            factors,
            tenant_id=event.tenant_id,
            website_id=event.website_id,
            environment_id=event.environment_id,
            path=event.path,
            bucket_start=bucket_start,
            factor_type=factor_type,
            observed_at=event.ingested_at or now,
            event_type=event.event_type,
            ip_hash=event.ip_hash,
        )

    anomaly_signals = (
        db.query(AnomalySignalEvent)
        .filter(AnomalySignalEvent.created_at >= window_start)
        .all()
    )
    for signal in anomaly_signals:
        factor_type = _map_anomaly_signal(signal.signal_type)
        if not factor_type:
            continue
        path = None
        if signal.summary and isinstance(signal.summary, dict):
            path = signal.summary.get("path")
        bucket_start = _truncate_hour(signal.created_at or now)
        _record_factor(
            factors,
            tenant_id=signal.tenant_id,
            website_id=signal.website_id,
            environment_id=signal.environment_id,
            path=path,
            bucket_start=bucket_start,
            factor_type=factor_type,
            observed_at=signal.created_at or now,
            event_type=signal.signal_type,
        )

    updated = 0
    for key, factor_map in factors.items():
        tenant_id, website_id, environment_id, path, bucket_start = key
        if bucket_start < recompute_cutoff and key in existing_snapshot_keys:
            continue

        db.query(TrustFactorAgg).filter(
            TrustFactorAgg.tenant_id == tenant_id,
            TrustFactorAgg.website_id == website_id,
            TrustFactorAgg.environment_id == environment_id,
            TrustFactorAgg.path == path,
            TrustFactorAgg.bucket_start == bucket_start,
        ).delete()
        db.query(TrustSnapshot).filter(
            TrustSnapshot.tenant_id == tenant_id,
            TrustSnapshot.website_id == website_id,
            TrustSnapshot.environment_id == environment_id,
            TrustSnapshot.path == path,
            TrustSnapshot.bucket_start == bucket_start,
        ).delete()

        risk_factors: list[RiskFactor] = []
        aggs_for_factors: list[tuple[FactorType, FactorSeverity, _FactorAggregate]] = []
        for factor_type, aggregate in factor_map.items():
            severity = _severity_for_count(aggregate.count)
            if severity is None:
                continue
            observed_at = aggregate.last_seen or bucket_start
            risk_factors.append(
                RiskFactor(
                    factor_type=factor_type,
                    severity=severity,
                    observed_at=observed_at,
                    last_seen_at=aggregate.last_seen,
                    evidence=aggregate.evidence(),
                )
            )
            aggs_for_factors.append((factor_type, severity, aggregate))

        trust_score = compute_trust_score(
            risk_factors,
            window_start=bucket_start,
            window_end=bucket_start + timedelta(hours=1),
        )

        snapshot = TrustSnapshot(
            tenant_id=tenant_id,
            website_id=website_id,
            environment_id=environment_id,
            bucket_start=bucket_start,
            path=path,
            trust_score=trust_score.score,
            confidence=trust_score.confidence,
            factor_count=len(trust_score.factors),
            created_at=now,
        )
        db.add(snapshot)

        for factor_type, severity, aggregate in aggs_for_factors:
            db.add(
                TrustFactorAgg(
                    tenant_id=tenant_id,
                    website_id=website_id,
                    environment_id=environment_id,
                    bucket_start=bucket_start,
                    path=path,
                    factor_type=factor_type.value,
                    severity=severity.value,
                    count=aggregate.count,
                    evidence_json=aggregate.evidence(),
                    created_at=now,
                )
            )

        updated += 1

    if updated:
        db.commit()
    return updated
