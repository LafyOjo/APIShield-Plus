from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.core.entitlements import resolve_effective_entitlements
from app.models.alerts import Alert
from app.models.audit_logs import AuditLog
from app.models.behaviour_events import BehaviourEvent
from app.models.events import Event
from app.models.geo_event_aggs import GeoEventAgg
from app.models.ip_enrichments import IPEnrichment
from app.models.enums import RoleEnum
from app.schemas.map import (
    MapDrilldownASN,
    MapDrilldownCity,
    MapDrilldownCountry,
    MapDrilldownIpHash,
    MapDrilldownPath,
    MapDrilldownResponse,
    MapSummaryPoint,
    MapSummaryResponse,
)
from app.tenancy.dependencies import require_role_in_tenant
from app.crud.tenants import get_tenant_by_id, get_tenant_by_slug


router = APIRouter(prefix="/map", tags=["map"])

_SUMMARY_CACHE: dict[tuple, tuple[float, list[MapSummaryPoint]]] = {}
_SUMMARY_CACHE_TTL_SECONDS = 60


def _coerce_positive_int(value) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _normalize_ts(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _clamp_time_window(
    from_ts: datetime | None,
    to_ts: datetime | None,
    max_days: int | None,
) -> tuple[datetime | None, datetime | None]:
    if max_days is None:
        return _normalize_ts(from_ts), _normalize_ts(to_ts)
    now = datetime.utcnow()
    max_range_start = now - timedelta(days=max_days)
    effective_to = _normalize_ts(to_ts) if to_ts and to_ts <= now else now
    effective_from = _normalize_ts(from_ts) if from_ts and from_ts >= max_range_start else max_range_start
    if effective_to < max_range_start:
        effective_to = now
    return effective_from, effective_to


def _resolve_tenant_id(db: Session, tenant_hint: str) -> int:
    if not tenant_hint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    tenant_value = tenant_hint.strip()
    tenant = (
        get_tenant_by_id(db, int(tenant_value))
        if tenant_value.isdigit()
        else get_tenant_by_slug(db, tenant_value)
    )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant.id


def _cache_get(key: tuple) -> list[MapSummaryPoint] | None:
    entry = _SUMMARY_CACHE.get(key)
    if not entry:
        return None
    cached_at, value = entry
    if monotonic() - cached_at > _SUMMARY_CACHE_TTL_SECONDS:
        _SUMMARY_CACHE.pop(key, None)
        return None
    return value


def _cache_set(key: tuple, value: list[MapSummaryPoint]) -> None:
    _SUMMARY_CACHE[key] = (monotonic(), value)


def _latlon_bounds(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    delta_lat = radius_km / 111.0
    cos_lat = math.cos(math.radians(lat))
    delta_lon = radius_km / (111.0 * cos_lat) if cos_lat else delta_lat
    return lat - delta_lat, lat + delta_lat, lon - delta_lon, lon + delta_lon


def _apply_time_filters(query, column, from_ts: datetime | None, to_ts: datetime | None):
    if from_ts:
        query = query.filter(column >= from_ts)
    if to_ts:
        query = query.filter(column <= to_ts)
    return query


def _apply_location_filter(query, *, country_code, lat, lon, radius_km):
    if country_code:
        return query.filter(GeoEventAgg.country_code == country_code)
    if lat is not None and lon is not None:
        radius = radius_km or 50.0
        min_lat, max_lat, min_lon, max_lon = _latlon_bounds(lat, lon, radius)
        return query.filter(
            GeoEventAgg.latitude >= min_lat,
            GeoEventAgg.latitude <= max_lat,
            GeoEventAgg.longitude >= min_lon,
            GeoEventAgg.longitude <= max_lon,
        )
    return query


def _apply_enrichment_location_filter(query, *, country_code, lat, lon, radius_km):
    if country_code:
        return query.filter(IPEnrichment.country_code == country_code)
    if lat is not None and lon is not None:
        radius = radius_km or 50.0
        min_lat, max_lat, min_lon, max_lon = _latlon_bounds(lat, lon, radius)
        return query.filter(
            IPEnrichment.latitude >= min_lat,
            IPEnrichment.latitude <= max_lat,
            IPEnrichment.longitude >= min_lon,
            IPEnrichment.longitude <= max_lon,
        )
    return query


def _select_model_for_category(category: str | None):
    if category in {None, "behaviour", "error"}:
        return BehaviourEvent, BehaviourEvent.ingested_at
    if category == "threat":
        return Alert, Alert.timestamp
    if category in {"login", "security"}:
        return Event, Event.timestamp
    if category == "audit":
        return AuditLog, AuditLog.timestamp
    return BehaviourEvent, BehaviourEvent.ingested_at


def _query_ip_hashes(
    db: Session,
    *,
    tenant_id: int,
    from_ts: datetime | None,
    to_ts: datetime | None,
    bucket_start: datetime | None,
    category: str | None,
    website_id: int | None,
    env_id: int | None,
    country_code: str | None,
    lat: float | None,
    lon: float | None,
    radius_km: float | None,
    limit: int = 20,
) -> list[MapDrilldownIpHash]:
    model, time_col = _select_model_for_category(category)

    if (website_id or env_id) and not hasattr(model, "website_id"):
        return []

    query = (
        db.query(model.ip_hash.label("ip_hash"), func.count().label("count"))
        .join(
            IPEnrichment,
            and_(model.tenant_id == IPEnrichment.tenant_id, model.ip_hash == IPEnrichment.ip_hash),
        )
        .filter(
            model.tenant_id == tenant_id,
            model.ip_hash.isnot(None),
            IPEnrichment.lookup_status == "ok",
        )
    )

    if hasattr(model, "website_id") and website_id:
        query = query.filter(model.website_id == website_id)
    if hasattr(model, "environment_id") and env_id:
        query = query.filter(model.environment_id == env_id)
    if category == "error" and model is BehaviourEvent:
        query = query.filter(BehaviourEvent.event_type == "error")
    query = _apply_time_filters(query, time_col, from_ts, to_ts)
    if bucket_start:
        query = query.filter(time_col >= bucket_start, time_col < bucket_start + timedelta(hours=1))
    query = _apply_enrichment_location_filter(
        query,
        country_code=country_code,
        lat=lat,
        lon=lon,
        radius_km=radius_km,
    )
    rows = (
        query.group_by(model.ip_hash)
        .order_by(func.count().desc())
        .limit(limit)
        .all()
    )
    return [MapDrilldownIpHash(ip_hash=row.ip_hash, count=int(row.count or 0)) for row in rows]


def _query_top_paths(
    db: Session,
    *,
    tenant_id: int,
    from_ts: datetime | None,
    to_ts: datetime | None,
    bucket_start: datetime | None,
    category: str | None,
    website_id: int | None,
    env_id: int | None,
    country_code: str | None,
    lat: float | None,
    lon: float | None,
    radius_km: float | None,
    limit: int = 10,
) -> list[MapDrilldownPath]:
    if category not in {None, "threat"}:
        return []
    if website_id or env_id:
        return []
    query = (
        db.query(Alert.request_path.label("path"), func.count().label("count"))
        .join(
            IPEnrichment,
            and_(Alert.tenant_id == IPEnrichment.tenant_id, Alert.ip_hash == IPEnrichment.ip_hash),
        )
        .filter(
            Alert.tenant_id == tenant_id,
            Alert.request_path.isnot(None),
            Alert.ip_hash.isnot(None),
            IPEnrichment.lookup_status == "ok",
        )
    )
    query = _apply_time_filters(query, Alert.timestamp, from_ts, to_ts)
    if bucket_start:
        query = query.filter(
            Alert.timestamp >= bucket_start,
            Alert.timestamp < bucket_start + timedelta(hours=1),
        )
    query = _apply_enrichment_location_filter(
        query,
        country_code=country_code,
        lat=lat,
        lon=lon,
        radius_km=radius_km,
    )
    rows = (
        query.group_by(Alert.request_path)
        .order_by(func.count().desc())
        .limit(limit)
        .all()
    )
    return [MapDrilldownPath(path=row.path, count=int(row.count or 0)) for row in rows if row.path]


@router.get("/summary", response_model=MapSummaryResponse)
def map_summary(
    from_ts: datetime | None = Query(None, alias="from"),
    to_ts: datetime | None = Query(None, alias="to"),
    website_id: int | None = None,
    env_id: int | None = None,
    category: str | None = None,
    severity: str | None = None,
    db: Session = Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.VIEWER], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    entitlements = resolve_effective_entitlements(db, tenant_id)
    features = entitlements.get("features", {})
    limits = entitlements.get("limits", {})
    geo_enabled = bool(features.get("geo_map"))
    max_geo_days = _coerce_positive_int(limits.get("geo_history_days"))
    if not geo_enabled:
        max_geo_days = 1
    from_ts, to_ts = _clamp_time_window(from_ts, to_ts, max_geo_days)

    cache_key = (
        str(db.get_bind().url),
        tenant_id,
        from_ts,
        to_ts,
        website_id,
        env_id,
        category,
        severity,
        geo_enabled,
    )
    cached = _cache_get(cache_key)
    if cached is not None:
        return MapSummaryResponse(items=cached)

    if geo_enabled:
        query = db.query(
            GeoEventAgg.latitude,
            GeoEventAgg.longitude,
            GeoEventAgg.country_code,
            GeoEventAgg.region,
            GeoEventAgg.city,
            GeoEventAgg.asn_number,
            GeoEventAgg.asn_org,
            GeoEventAgg.is_datacenter,
            func.sum(GeoEventAgg.count).label("count"),
        )
    else:
        query = db.query(
            GeoEventAgg.country_code,
            func.sum(GeoEventAgg.count).label("count"),
        )

    query = query.filter(GeoEventAgg.tenant_id == tenant_id)
    if website_id:
        query = query.filter(GeoEventAgg.website_id == website_id)
    if env_id:
        query = query.filter(GeoEventAgg.environment_id == env_id)
    if category:
        query = query.filter(GeoEventAgg.event_category == category)
    if severity:
        query = query.filter(GeoEventAgg.severity == severity)
    query = _apply_time_filters(query, GeoEventAgg.bucket_start, from_ts, to_ts)

    if geo_enabled:
        query = query.group_by(
            GeoEventAgg.latitude,
            GeoEventAgg.longitude,
            GeoEventAgg.country_code,
            GeoEventAgg.region,
            GeoEventAgg.city,
            GeoEventAgg.asn_number,
            GeoEventAgg.asn_org,
            GeoEventAgg.is_datacenter,
        )
    else:
        query = query.group_by(GeoEventAgg.country_code)
    rows = query.order_by(func.sum(GeoEventAgg.count).desc()).all()

    items: list[MapSummaryPoint] = []
    if geo_enabled:
        for row in rows:
            items.append(
                MapSummaryPoint(
                    count=int(row.count or 0),
                    latitude=row.latitude,
                    longitude=row.longitude,
                    country_code=row.country_code,
                    region=row.region,
                    city=row.city,
                    asn_number=row.asn_number,
                    asn_org=row.asn_org,
                    is_datacenter=row.is_datacenter,
                )
            )
    else:
        for row in rows:
            items.append(
                MapSummaryPoint(
                    count=int(row.count or 0),
                    country_code=row.country_code,
                )
            )

    _cache_set(cache_key, items)
    return MapSummaryResponse(items=items)


@router.get("/drilldown", response_model=MapDrilldownResponse)
def map_drilldown(
    from_ts: datetime | None = Query(None, alias="from"),
    to_ts: datetime | None = Query(None, alias="to"),
    website_id: int | None = None,
    env_id: int | None = None,
    category: str | None = None,
    severity: str | None = None,
    bucket_start: datetime | None = None,
    country_code: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    radius_km: float | None = None,
    db: Session = Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.VIEWER], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    entitlements = resolve_effective_entitlements(db, tenant_id)
    features = entitlements.get("features", {})
    limits = entitlements.get("limits", {})
    geo_enabled = bool(features.get("geo_map"))
    max_geo_days = _coerce_positive_int(limits.get("geo_history_days"))
    if not geo_enabled:
        max_geo_days = 1
    from_ts, to_ts = _clamp_time_window(from_ts, to_ts, max_geo_days)

    base_query = db.query(GeoEventAgg).filter(GeoEventAgg.tenant_id == tenant_id)
    if website_id:
        base_query = base_query.filter(GeoEventAgg.website_id == website_id)
    if env_id:
        base_query = base_query.filter(GeoEventAgg.environment_id == env_id)
    if category:
        base_query = base_query.filter(GeoEventAgg.event_category == category)
    if severity:
        base_query = base_query.filter(GeoEventAgg.severity == severity)
    base_query = _apply_time_filters(base_query, GeoEventAgg.bucket_start, from_ts, to_ts)
    if bucket_start:
        bucket_start = _normalize_ts(bucket_start)
        base_query = base_query.filter(GeoEventAgg.bucket_start == bucket_start)
    base_query = _apply_location_filter(
        base_query,
        country_code=country_code,
        lat=lat,
        lon=lon,
        radius_km=radius_km,
    )

    countries_rows = (
        base_query.with_entities(
            GeoEventAgg.country_code.label("country_code"),
            func.sum(GeoEventAgg.count).label("count"),
        )
        .group_by(GeoEventAgg.country_code)
        .order_by(func.sum(GeoEventAgg.count).desc())
        .limit(20)
        .all()
    )
    countries = [
        MapDrilldownCountry(country_code=row.country_code, count=int(row.count or 0))
        for row in countries_rows
        if row.country_code or row.count
    ]

    cities: list[MapDrilldownCity] = []
    asns: list[MapDrilldownASN] = []
    ip_hashes: list[MapDrilldownIpHash] = []
    paths: list[MapDrilldownPath] = []

    if geo_enabled:
        city_rows = (
            base_query.with_entities(
                GeoEventAgg.country_code,
                GeoEventAgg.region,
                GeoEventAgg.city,
                func.sum(GeoEventAgg.count).label("count"),
            )
            .group_by(GeoEventAgg.country_code, GeoEventAgg.region, GeoEventAgg.city)
            .order_by(func.sum(GeoEventAgg.count).desc())
            .limit(50)
            .all()
        )
        cities = [
            MapDrilldownCity(
                country_code=row.country_code,
                region=row.region,
                city=row.city,
                count=int(row.count or 0),
            )
            for row in city_rows
            if row.city or row.region or row.country_code
        ]

        asn_rows = (
            base_query.with_entities(
                GeoEventAgg.asn_number,
                GeoEventAgg.asn_org,
                func.sum(GeoEventAgg.count).label("count"),
            )
            .group_by(GeoEventAgg.asn_number, GeoEventAgg.asn_org)
            .order_by(func.sum(GeoEventAgg.count).desc())
            .limit(50)
            .all()
        )
        asns = [
            MapDrilldownASN(
                asn_number=row.asn_number,
                asn_org=row.asn_org,
                count=int(row.count or 0),
            )
            for row in asn_rows
            if row.asn_number or row.asn_org
        ]

        ip_hashes = _query_ip_hashes(
            db,
            tenant_id=tenant_id,
            from_ts=from_ts,
            to_ts=to_ts,
            bucket_start=bucket_start,
            category=category,
            website_id=website_id,
            env_id=env_id,
            country_code=country_code,
            lat=lat,
            lon=lon,
            radius_km=radius_km,
        )
        paths = _query_top_paths(
            db,
            tenant_id=tenant_id,
            from_ts=from_ts,
            to_ts=to_ts,
            bucket_start=bucket_start,
            category=category,
            website_id=website_id,
            env_id=env_id,
            country_code=country_code,
            lat=lat,
            lon=lon,
            radius_km=radius_km,
        )

    return MapDrilldownResponse(
        countries=countries,
        cities=cities,
        asns=asns,
        ip_hashes=ip_hashes,
        paths=paths,
    )
