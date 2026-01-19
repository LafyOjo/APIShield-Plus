from __future__ import annotations

from datetime import timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import utcnow
from app.geo.provider import GeoResult, get_geo_provider
from app.models.ip_enrichments import IPEnrichment


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


def _apply_result(record: IPEnrichment, result: GeoResult) -> None:
    record.country_code = result.country_code
    record.region = result.region
    record.city = result.city
    record.latitude = result.latitude
    record.longitude = result.longitude
    record.asn_number = result.asn_number
    record.asn_org = result.asn_org
    record.is_datacenter = result.is_datacenter


def mark_ip_seen(db: Session, tenant_id: int, ip_hash: str) -> IPEnrichment:
    if tenant_id is None or not ip_hash:
        raise ValueError("tenant_id and ip_hash are required")
    now = utcnow()
    record = (
        db.query(IPEnrichment)
        .filter(IPEnrichment.tenant_id == tenant_id, IPEnrichment.ip_hash == ip_hash)
        .first()
    )
    if record:
        record.last_seen_at = now
        if record.first_seen_at is None:
            record.first_seen_at = now
    else:
        record = IPEnrichment(
            tenant_id=tenant_id,
            ip_hash=ip_hash,
            first_seen_at=now,
            last_seen_at=now,
            lookup_status="pending",
        )
        db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        record = (
            db.query(IPEnrichment)
            .filter(IPEnrichment.tenant_id == tenant_id, IPEnrichment.ip_hash == ip_hash)
            .first()
        )
        if record:
            record.last_seen_at = now
            if record.first_seen_at is None:
                record.first_seen_at = now
            db.commit()
    if record is None:
        raise ValueError("Failed to record enrichment")
    db.refresh(record)
    return record


def get_or_lookup_enrichment(
    db: Session,
    tenant_id: int,
    ip_hash: str,
    client_ip: str | None = None,
) -> IPEnrichment | None:
    if tenant_id is None or not ip_hash:
        raise ValueError("tenant_id and ip_hash are required")
    now = utcnow()
    record = (
        db.query(IPEnrichment)
        .filter(IPEnrichment.tenant_id == tenant_id, IPEnrichment.ip_hash == ip_hash)
        .first()
    )
    if record:
        record.last_seen_at = now
        if record.first_seen_at is None:
            record.first_seen_at = now
        if _is_fresh(record, now):
            db.commit()
            db.refresh(record)
            return record

    if not client_ip:
        if record:
            db.commit()
            db.refresh(record)
        return record

    try:
        provider = get_geo_provider()
        result = provider.lookup(client_ip)
        if record is None:
            record = IPEnrichment(
                tenant_id=tenant_id,
                ip_hash=ip_hash,
                first_seen_at=now,
                last_seen_at=now,
            )
            db.add(record)
        record.last_seen_at = now
        record.last_lookup_at = now
        record.source = settings.GEO_PROVIDER
        record.lookup_status = "ok"
        record.failure_reason = None
        _apply_result(record, result)
        db.commit()
        db.refresh(record)
        return record
    except Exception as exc:
        if record is None:
            record = IPEnrichment(
                tenant_id=tenant_id,
                ip_hash=ip_hash,
                first_seen_at=now,
                last_seen_at=now,
            )
            db.add(record)
        record.last_seen_at = now
        record.last_lookup_at = now
        record.source = settings.GEO_PROVIDER
        record.lookup_status = "failed"
        record.failure_reason = str(exc)
        try:
            db.commit()
            db.refresh(record)
        except IntegrityError:
            db.rollback()
        return record
