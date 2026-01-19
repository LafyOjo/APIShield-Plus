from __future__ import annotations

import argparse
import logging
from datetime import timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.time import utcnow
from app.geo.enrichment import get_or_lookup_enrichment, mark_ip_seen
from app.models.alerts import Alert
from app.models.audit_logs import AuditLog
from app.models.behaviour_events import BehaviourEvent
from app.models.events import Event
from app.models.ip_enrichments import IPEnrichment


logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK_MINUTES = 15
DEFAULT_MAX_ITEMS = 1000
FAILURE_BACKOFF_MINUTES = 15


def _ensure_aware(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _is_fresh(record: IPEnrichment, now) -> bool:
    ttl_days = max(0, int(settings.GEO_ENRICHMENT_TTL_DAYS))
    last_lookup = _ensure_aware(record.last_lookup_at)
    if not last_lookup:
        return False
    return last_lookup >= now - timedelta(days=ttl_days)


def _is_in_backoff(record: IPEnrichment, now) -> bool:
    last_lookup = _ensure_aware(record.last_lookup_at)
    if not last_lookup or record.lookup_status != "failed":
        return False
    return last_lookup >= now - timedelta(minutes=FAILURE_BACKOFF_MINUTES)


def _latest_client_ip(db: Session, tenant_id: int, ip_hash: str) -> str | None:
    best_ip = None
    best_ts = None

    def consider(row):
        nonlocal best_ip, best_ts
        if row and row[0]:
            ip, ts = row
            if ts and (best_ts is None or ts > best_ts):
                best_ip = ip
                best_ts = ts

    alert = (
        db.query(Alert.client_ip, Alert.timestamp)
        .filter(
            Alert.tenant_id == tenant_id,
            Alert.ip_hash == ip_hash,
            Alert.client_ip.isnot(None),
        )
        .order_by(Alert.timestamp.desc())
        .first()
    )
    consider(alert)

    event = (
        db.query(Event.client_ip, Event.timestamp)
        .filter(
            Event.tenant_id == tenant_id,
            Event.ip_hash == ip_hash,
            Event.client_ip.isnot(None),
        )
        .order_by(Event.timestamp.desc())
        .first()
    )
    consider(event)

    audit = (
        db.query(AuditLog.client_ip, AuditLog.timestamp)
        .filter(
            AuditLog.tenant_id == tenant_id,
            AuditLog.ip_hash == ip_hash,
            AuditLog.client_ip.isnot(None),
        )
        .order_by(AuditLog.timestamp.desc())
        .first()
    )
    consider(audit)

    return best_ip


def _candidate_ip_hashes(db: Session, since) -> list[tuple[int, str]]:
    candidates: set[tuple[int, str]] = set()
    behaviour_rows = (
        db.query(BehaviourEvent.tenant_id, BehaviourEvent.ip_hash)
        .filter(
            BehaviourEvent.ingested_at >= since,
            BehaviourEvent.ip_hash.isnot(None),
        )
        .distinct()
        .all()
    )
    for tenant_id, ip_hash in behaviour_rows:
        if tenant_id is None or not ip_hash:
            continue
        candidates.add((tenant_id, ip_hash))

    alert_rows = (
        db.query(Alert.tenant_id, Alert.ip_hash)
        .filter(
            Alert.timestamp >= since,
            Alert.tenant_id.isnot(None),
            Alert.ip_hash.isnot(None),
        )
        .distinct()
        .all()
    )
    for tenant_id, ip_hash in alert_rows:
        if tenant_id is None or not ip_hash:
            continue
        candidates.add((tenant_id, ip_hash))

    return list(candidates)


def run_geo_enrichment(
    db: Session,
    *,
    lookback_minutes: int = DEFAULT_LOOKBACK_MINUTES,
    max_items: int = DEFAULT_MAX_ITEMS,
) -> int:
    now = utcnow()
    since = now - timedelta(minutes=max(1, lookback_minutes))
    candidates = _candidate_ip_hashes(db, since)
    processed = 0

    for tenant_id, ip_hash in candidates:
        if processed >= max_items:
            break
        record = (
            db.query(IPEnrichment)
            .filter(IPEnrichment.tenant_id == tenant_id, IPEnrichment.ip_hash == ip_hash)
            .first()
        )
        if record and _is_fresh(record, now) and record.lookup_status == "ok":
            continue
        if record and _is_in_backoff(record, now):
            continue

        client_ip = _latest_client_ip(db, tenant_id, ip_hash)
        if not client_ip:
            try:
                mark_ip_seen(db, tenant_id, ip_hash)
            except Exception:
                logger.exception("Failed to update geo enrichment seed")
            continue

        try:
            get_or_lookup_enrichment(
                db,
                tenant_id=tenant_id,
                ip_hash=ip_hash,
                client_ip=client_ip,
            )
        except Exception:
            logger.exception("Geo lookup failed for tenant %s ip_hash %s", tenant_id, ip_hash)
        processed += 1

    return processed


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run geo enrichment job.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single enrichment pass and exit.",
    )
    parser.add_argument(
        "--lookback-minutes",
        type=int,
        default=DEFAULT_LOOKBACK_MINUTES,
        help="How far back to scan for missing enrichments.",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=DEFAULT_MAX_ITEMS,
        help="Maximum number of lookups per run.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    with SessionLocal() as db:
        processed = run_geo_enrichment(
            db,
            lookback_minutes=args.lookback_minutes,
            max_items=args.max_items,
        )
    logger.info("Geo enrichment run complete. processed=%s", processed)
    if args.once:
        return


if __name__ == "__main__":
    main()
