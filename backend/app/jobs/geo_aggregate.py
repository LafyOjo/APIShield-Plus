from __future__ import annotations

import argparse
import logging
from datetime import timedelta, timezone
from typing import Any

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.entitlements import resolve_effective_entitlements
from app.core.db import SessionLocal
from app.core.time import utcnow
from app.models.alerts import Alert
from app.models.behaviour_events import BehaviourEvent
from app.models.events import Event
from app.models.geo_event_aggs import GeoEventAgg
from app.models.ip_enrichments import IPEnrichment
from app.models.security_events import SecurityEvent
from app.security.taxonomy import (
    SecurityEventTypeEnum,
    SecurityCategoryEnum,
    SeverityEnum,
    get_category,
    get_severity,
)


logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK_MINUTES = 60
DEFAULT_MAX_BUCKETS = 5000
BEHAVIOUR_CATEGORY = "behaviour"


def _ensure_aware(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _bucket_start(value):
    value = _ensure_aware(value)
    if value is None:
        return None
    return value.replace(minute=0, second=0, microsecond=0)


def _country_only_mode(db: Session, tenant_id: int) -> bool:
    try:
        entitlements = resolve_effective_entitlements(db, tenant_id)
    except Exception:
        return True
    features = entitlements.get("features", {}) if entitlements else {}
    return not bool(features.get("geo_map"))


def _apply_granularity(row: dict[str, Any], country_only: bool) -> dict[str, Any]:
    if not country_only:
        return row
    row = dict(row)
    row["region"] = None
    row["city"] = None
    row["latitude"] = None
    row["longitude"] = None
    row["asn_number"] = None
    row["asn_org"] = None
    row["is_datacenter"] = None
    return row


def _coerce_category(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return SecurityCategoryEnum(value).value
    except ValueError:
        return None


def _coerce_severity(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return SeverityEnum(value).value
    except ValueError:
        return None


def _map_event_action(action: str | None, success: bool | None) -> SecurityEventTypeEnum | None:
    normalized = (action or "").lower()
    if "login" in normalized:
        return (
            SecurityEventTypeEnum.LOGIN_ATTEMPT_FAILED
            if success is False
            else SecurityEventTypeEnum.LOGIN_ATTEMPT
        )
    if "stuffing" in normalized:
        if "block" in normalized:
            return SecurityEventTypeEnum.CREDENTIAL_STUFFING_BLOCKED
        return SecurityEventTypeEnum.CREDENTIAL_STUFFING
    return None


def _map_alert_type(detail: str | None) -> SecurityEventTypeEnum:
    normalized = (detail or "").lower()
    if "blocked" in normalized:
        return SecurityEventTypeEnum.CREDENTIAL_STUFFING_BLOCKED
    return SecurityEventTypeEnum.BRUTE_FORCE


def _map_behaviour_category(event_type: str | None) -> str:
    normalized = (event_type or "").lower()
    if normalized == "error":
        return SecurityCategoryEnum.ANOMALY.value
    return BEHAVIOUR_CATEGORY


def _iter_behaviour_rows(db: Session, since):
    rows = (
        db.query(
            BehaviourEvent.tenant_id,
            BehaviourEvent.website_id,
            BehaviourEvent.environment_id,
            BehaviourEvent.event_ts.label("event_time"),
            BehaviourEvent.event_type,
            IPEnrichment.country_code,
            IPEnrichment.region,
            IPEnrichment.city,
            IPEnrichment.latitude,
            IPEnrichment.longitude,
            IPEnrichment.asn_number,
            IPEnrichment.asn_org,
            IPEnrichment.is_datacenter,
        )
        .join(
            IPEnrichment,
            and_(
                BehaviourEvent.tenant_id == IPEnrichment.tenant_id,
                BehaviourEvent.ip_hash == IPEnrichment.ip_hash,
            ),
        )
        .filter(
            BehaviourEvent.event_ts >= since,
            BehaviourEvent.ip_hash.isnot(None),
            IPEnrichment.lookup_status == "ok",
        )
        .all()
    )
    for row in rows:
        category = _map_behaviour_category(row.event_type)
        yield {
            "tenant_id": row.tenant_id,
            "website_id": row.website_id,
            "environment_id": row.environment_id,
            "event_time": row.event_time,
            "event_category": category,
            "severity": None,
            "country_code": row.country_code,
            "region": row.region,
            "city": row.city,
            "latitude": row.latitude,
            "longitude": row.longitude,
            "asn_number": row.asn_number,
            "asn_org": row.asn_org,
            "is_datacenter": row.is_datacenter,
        }


def _iter_security_event_rows(db: Session, since):
    event_time_expr = func.coalesce(SecurityEvent.event_ts, SecurityEvent.created_at).label("event_time")
    rows = (
        db.query(
            SecurityEvent.tenant_id,
            SecurityEvent.website_id,
            SecurityEvent.environment_id,
            event_time_expr,
            SecurityEvent.category,
            SecurityEvent.severity,
            IPEnrichment.country_code,
            IPEnrichment.region,
            IPEnrichment.city,
            IPEnrichment.latitude,
            IPEnrichment.longitude,
            IPEnrichment.asn_number,
            IPEnrichment.asn_org,
            IPEnrichment.is_datacenter,
        )
        .join(
            IPEnrichment,
            and_(
                SecurityEvent.tenant_id == IPEnrichment.tenant_id,
                SecurityEvent.ip_hash == IPEnrichment.ip_hash,
            ),
        )
        .filter(
            event_time_expr >= since,
            SecurityEvent.ip_hash.isnot(None),
            IPEnrichment.lookup_status == "ok",
        )
        .all()
    )
    for row in rows:
        category = _coerce_category(row.category)
        severity = _coerce_severity(row.severity)
        if not category or not severity:
            continue
        yield {
            "tenant_id": row.tenant_id,
            "website_id": row.website_id,
            "environment_id": row.environment_id,
            "event_time": row.event_time,
            "event_category": category,
            "severity": severity,
            "country_code": row.country_code,
            "region": row.region,
            "city": row.city,
            "latitude": row.latitude,
            "longitude": row.longitude,
            "asn_number": row.asn_number,
            "asn_org": row.asn_org,
            "is_datacenter": row.is_datacenter,
        }


def _iter_alert_rows(db: Session, since):
    rows = (
        db.query(
            Alert.tenant_id,
            Alert.timestamp,
            Alert.detail,
            IPEnrichment.country_code,
            IPEnrichment.region,
            IPEnrichment.city,
            IPEnrichment.latitude,
            IPEnrichment.longitude,
            IPEnrichment.asn_number,
            IPEnrichment.asn_org,
            IPEnrichment.is_datacenter,
        )
        .join(
            IPEnrichment,
            and_(Alert.tenant_id == IPEnrichment.tenant_id, Alert.ip_hash == IPEnrichment.ip_hash),
        )
        .filter(
            Alert.timestamp >= since,
            Alert.tenant_id.isnot(None),
            Alert.ip_hash.isnot(None),
            IPEnrichment.lookup_status == "ok",
        )
        .all()
    )
    for row in rows:
        event_type = _map_alert_type(row.detail)
        category = get_category(event_type).value
        severity = get_severity(event_type).value
        yield {
            "tenant_id": row.tenant_id,
            "website_id": None,
            "environment_id": None,
            "event_time": row.timestamp,
            "event_category": category,
            "severity": severity,
            "country_code": row.country_code,
            "region": row.region,
            "city": row.city,
            "latitude": row.latitude,
            "longitude": row.longitude,
            "asn_number": row.asn_number,
            "asn_org": row.asn_org,
            "is_datacenter": row.is_datacenter,
        }


def _iter_event_rows(db: Session, since):
    rows = (
        db.query(
            Event.tenant_id,
            Event.timestamp,
            Event.action,
            Event.success,
            IPEnrichment.country_code,
            IPEnrichment.region,
            IPEnrichment.city,
            IPEnrichment.latitude,
            IPEnrichment.longitude,
            IPEnrichment.asn_number,
            IPEnrichment.asn_org,
            IPEnrichment.is_datacenter,
        )
        .join(
            IPEnrichment,
            and_(Event.tenant_id == IPEnrichment.tenant_id, Event.ip_hash == IPEnrichment.ip_hash),
        )
        .filter(
            Event.timestamp >= since,
            Event.ip_hash.isnot(None),
            IPEnrichment.lookup_status == "ok",
        )
        .all()
    )
    for row in rows:
        event_type = _map_event_action(row.action, row.success)
        if not event_type:
            continue
        category = get_category(event_type).value
        severity = get_severity(event_type).value
        yield {
            "tenant_id": row.tenant_id,
            "website_id": None,
            "environment_id": None,
            "event_time": row.timestamp,
            "event_category": category,
            "severity": severity,
            "country_code": row.country_code,
            "region": row.region,
            "city": row.city,
            "latitude": row.latitude,
            "longitude": row.longitude,
            "asn_number": row.asn_number,
            "asn_org": row.asn_org,
            "is_datacenter": row.is_datacenter,
        }


def run_geo_aggregate(
    db: Session,
    *,
    lookback_minutes: int = DEFAULT_LOOKBACK_MINUTES,
    max_buckets: int = DEFAULT_MAX_BUCKETS,
) -> int:
    now = utcnow()
    since = now - timedelta(minutes=max(1, lookback_minutes))
    aggregates: dict[tuple, int] = {}
    tenant_modes: dict[int, bool] = {}

    def add_row(row: dict[str, Any]) -> None:
        tenant_id = row["tenant_id"]
        if tenant_id is None:
            return
        if tenant_id not in tenant_modes:
            tenant_modes[tenant_id] = _country_only_mode(db, tenant_id)
        row = _apply_granularity(row, tenant_modes[tenant_id])
        bucket_start = _bucket_start(row["event_time"])
        if bucket_start is None:
            return
        key = (
            tenant_id,
            row["website_id"],
            row["environment_id"],
            bucket_start,
            row["event_category"],
            row["severity"],
            row["country_code"],
            row["region"],
            row["city"],
            row["latitude"],
            row["longitude"],
            row["asn_number"],
            row["asn_org"],
            row["is_datacenter"],
        )
        aggregates[key] = aggregates.get(key, 0) + 1

    for row in _iter_security_event_rows(db, since):
        add_row(row)
    for row in _iter_behaviour_rows(db, since):
        add_row(row)
    for row in _iter_alert_rows(db, since):
        add_row(row)
    for row in _iter_event_rows(db, since):
        add_row(row)

    updated = 0
    for key, count in aggregates.items():
        if updated >= max_buckets:
            break
        (
            tenant_id,
            website_id,
            environment_id,
            bucket_start,
            event_category,
            severity,
            country_code,
            region,
            city,
            latitude,
            longitude,
            asn_number,
            asn_org,
            is_datacenter,
        ) = key
        existing = (
            db.query(GeoEventAgg)
            .filter(
                GeoEventAgg.tenant_id == tenant_id,
                GeoEventAgg.website_id == website_id,
                GeoEventAgg.environment_id == environment_id,
                GeoEventAgg.bucket_start == bucket_start,
                GeoEventAgg.event_category == event_category,
                GeoEventAgg.severity == severity,
                GeoEventAgg.country_code == country_code,
                GeoEventAgg.region == region,
                GeoEventAgg.city == city,
                GeoEventAgg.latitude == latitude,
                GeoEventAgg.longitude == longitude,
                GeoEventAgg.asn_number == asn_number,
                GeoEventAgg.asn_org == asn_org,
                GeoEventAgg.is_datacenter == is_datacenter,
            )
            .first()
        )
        if existing:
            existing.count = count
        else:
            db.add(
                GeoEventAgg(
                    tenant_id=tenant_id,
                    website_id=website_id,
                    environment_id=environment_id,
                    bucket_start=bucket_start,
                    event_category=event_category,
                    severity=severity,
                    country_code=country_code,
                    region=region,
                    city=city,
                    latitude=latitude,
                    longitude=longitude,
                    asn_number=asn_number,
                    asn_org=asn_org,
                    is_datacenter=is_datacenter,
                    count=count,
                )
            )
        updated += 1

    if updated:
        db.commit()
    return updated


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run geo aggregation job.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single aggregation pass and exit.",
    )
    parser.add_argument(
        "--lookback-minutes",
        type=int,
        default=DEFAULT_LOOKBACK_MINUTES,
        help="How far back to scan for events.",
    )
    parser.add_argument(
        "--max-buckets",
        type=int,
        default=DEFAULT_MAX_BUCKETS,
        help="Maximum number of buckets to upsert per run.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    with SessionLocal() as db:
        updated = run_geo_aggregate(
            db,
            lookback_minutes=args.lookback_minutes,
            max_buckets=args.max_buckets,
        )
    logger.info("Geo aggregation run complete. updated=%s", updated)
    if args.once:
        return


if __name__ == "__main__":
    main()
