from __future__ import annotations

import argparse
import json
import logging
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.retention import DATASET_RETENTION_LIMIT_KEYS
from app.core.time import utcnow
from app.entitlements.resolver import resolve_entitlements_for_tenant
from app.crud.tenant_retention_policies import get_policies
from app.models.audit_logs import AuditLog
from app.models.behaviour_events import BehaviourEvent
from app.models.geo_event_aggs import GeoEventAgg
from app.models.incidents import Incident
from app.models.retention_runs import RetentionRun
from app.models.tenants import Tenant
from app.models.security_events import SecurityEvent


logger = logging.getLogger(__name__)

DATASET_TABLES = {
    "behaviour_events": (BehaviourEvent, BehaviourEvent.ingested_at),
    "security_events": (SecurityEvent, SecurityEvent.created_at),
    "incidents": (Incident, Incident.last_seen_at),
    "audit_logs": (AuditLog, AuditLog.timestamp),
    "geo_agg": (GeoEventAgg, GeoEventAgg.bucket_start),
}


def _coerce_positive_int(value) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _effective_retention_days(dataset_key: str, desired_days: int, limits: dict) -> int:
    limit_key = DATASET_RETENTION_LIMIT_KEYS.get(dataset_key)
    if isinstance(limit_key, (list, tuple)):
        max_allowed = None
        for key in limit_key:
            max_allowed = _coerce_positive_int(limits.get(key))
            if max_allowed is not None:
                break
    else:
        max_allowed = _coerce_positive_int(limits.get(limit_key)) if limit_key else None
    if max_allowed is None:
        return desired_days
    return min(desired_days, max_allowed)


def run_retention_for_tenant(db: Session, tenant_id: int) -> RetentionRun:
    now = utcnow()
    entitlements = resolve_entitlements_for_tenant(db, tenant_id, use_cache=False)
    limits = entitlements.get("limits", {}) if entitlements else {}
    policies = get_policies(db, tenant_id, ensure_defaults=True, plan_limits=limits)

    event_retention_days = _coerce_positive_int(
        limits.get("event_retention_days") or limits.get("retention_days")
    ) or 0
    raw_ip_retention_days = _coerce_positive_int(limits.get("raw_ip_retention_days")) or 0

    run = RetentionRun(
        tenant_id=tenant_id,
        started_at=now,
        status="running",
        event_retention_days=event_retention_days,
        raw_ip_retention_days=raw_ip_retention_days,
        behaviour_events_deleted=0,
        security_events_deleted=0,
        alerts_raw_ip_scrubbed=0,
        events_raw_ip_scrubbed=0,
        audit_logs_raw_ip_scrubbed=0,
        security_events_raw_ip_scrubbed=0,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    deleted_counts: dict[str, int] = {}
    skipped: list[str] = []

    try:
        for policy in policies:
            dataset_key = policy.dataset_key
            if dataset_key not in DATASET_TABLES:
                continue
            if policy.is_legal_hold_enabled:
                skipped.append(dataset_key)
                continue
            desired = int(policy.retention_days)
            effective_days = _effective_retention_days(dataset_key, desired, limits)
            cutoff = now - timedelta(days=effective_days)
            model, timestamp_col = DATASET_TABLES[dataset_key]
            deleted = (
                db.query(model)
                .filter(model.tenant_id == tenant_id, timestamp_col < cutoff)
                .delete(synchronize_session=False)
            )
            deleted_counts[dataset_key] = int(deleted or 0)

        run.behaviour_events_deleted = deleted_counts.get("behaviour_events", 0)
        run.security_events_deleted = deleted_counts.get("security_events", 0)
        summary = {"deleted": deleted_counts, "skipped": sorted(skipped)}
        if deleted_counts or skipped:
            run.error_message = json.dumps(summary, separators=(",", ":"))
        run.status = "completed"
        run.finished_at = utcnow()
        db.commit()
        db.refresh(run)
        return run
    except Exception as exc:
        run.status = "failed"
        run.error_message = str(exc)
        run.finished_at = utcnow()
        db.commit()
        db.refresh(run)
        logger.exception("Retention job failed for tenant %s", tenant_id)
        raise


def run_retention_all_tenants(db: Session) -> int:
    tenant_ids = [row[0] for row in db.query(Tenant.id).all()]
    processed = 0
    for tenant_id in tenant_ids:
        run_retention_for_tenant(db, tenant_id)
        processed += 1
    return processed


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run retention cleanup job.")
    parser.add_argument("--tenant-id", type=int, default=None, help="Run for a single tenant.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    with SessionLocal() as db:
        if args.tenant_id:
            run_retention_for_tenant(db, args.tenant_id)
        else:
            run_retention_all_tenants(db)


if __name__ == "__main__":
    main()
