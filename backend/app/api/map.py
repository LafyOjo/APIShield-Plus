from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.cache import build_cache_key, cache_get, cache_set, db_scope_id
from app.core.config import settings
from app.core.db import get_db
from app.core.entitlements import resolve_effective_entitlements
from app.core.tracing import trace_span
from app.entitlements.enforcement import clamp_range
from app.models.alerts import Alert
from app.models.events import Event
from app.models.geo_event_aggs import GeoEventAgg
from app.models.ip_enrichments import IPEnrichment
from app.models.security_events import SecurityEvent
from app.models.enums import RoleEnum
from app.security.taxonomy import SecurityCategoryEnum
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
from app.models.tenants import Tenant


router = APIRouter(prefix="/map", tags=["map"])

LEGACY_CATEGORY_MAP = {
    "behaviour": None,
    "error": SecurityCategoryEnum.INTEGRITY.value,
    "audit": SecurityCategoryEnum.INTEGRITY.value,
    "security": SecurityCategoryEnum.THREAT.value,
}


def _coerce_positive_int(value) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _normalize_category(category: str | None) -> str | None:
    if not category:
        return None
    normalized = category.strip().lower()
    if normalized in LEGACY_CATEGORY_MAP:
        return LEGACY_CATEGORY_MAP[normalized]
    try:
        return SecurityCategoryEnum(normalized).value
    except ValueError:
        return None


def _normalize_ts(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _resolve_tenant(db: Session, tenant_hint: str) -> Tenant:
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
    return tenant


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
    include_demo: bool,
    limit: int = 20,
) -> list[MapDrilldownIpHash]:
    normalized_category = _normalize_category(category)
    sources: list[tuple[object, object, list]] = []

    if normalized_category == SecurityCategoryEnum.LOGIN.value:
        sources.append((Event, Event.timestamp, [Event.action.ilike("%login%")]))
        time_col = func.coalesce(SecurityEvent.event_ts, SecurityEvent.created_at)
        sources.append(
            (
                SecurityEvent,
                time_col,
                [SecurityEvent.category == SecurityCategoryEnum.LOGIN.value],
            )
        )
    elif normalized_category == SecurityCategoryEnum.THREAT.value:
        sources.append((Alert, Alert.timestamp, []))
        sources.append((Event, Event.timestamp, [Event.action.ilike("%stuffing%")]))
        time_col = func.coalesce(SecurityEvent.event_ts, SecurityEvent.created_at)
        sources.append(
            (
                SecurityEvent,
                time_col,
                [SecurityEvent.category == SecurityCategoryEnum.THREAT.value],
            )
        )
    elif normalized_category in {
        SecurityCategoryEnum.INTEGRITY.value,
        SecurityCategoryEnum.BOT.value,
        SecurityCategoryEnum.ANOMALY.value,
    }:
        time_col = func.coalesce(SecurityEvent.event_ts, SecurityEvent.created_at)
        sources.append(
            (
                SecurityEvent,
                time_col,
                [SecurityEvent.category == normalized_category],
            )
        )
    else:
        sources.append((Event, Event.timestamp, []))
        sources.append((Alert, Alert.timestamp, []))

    ip_counts: dict[str, int] = {}

    for model, time_col, extra_filters in sources:
        if (website_id or env_id) and not hasattr(model, "website_id"):
            continue
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
        if hasattr(model, "is_demo") and not include_demo:
            query = query.filter(model.is_demo.is_(False))
        if hasattr(IPEnrichment, "is_demo") and not include_demo:
            query = query.filter(IPEnrichment.is_demo.is_(False))
        if hasattr(model, "website_id") and website_id:
            query = query.filter(model.website_id == website_id)
        if hasattr(model, "environment_id") and env_id:
            query = query.filter(model.environment_id == env_id)
        if extra_filters:
            query = query.filter(*extra_filters)
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
        rows = query.group_by(model.ip_hash).order_by(func.count().desc()).limit(limit).all()
        for row in rows:
            if not row.ip_hash:
                continue
            ip_counts[row.ip_hash] = ip_counts.get(row.ip_hash, 0) + int(row.count or 0)

    sorted_rows = sorted(ip_counts.items(), key=lambda item: item[1], reverse=True)[:limit]
    return [MapDrilldownIpHash(ip_hash=ip_hash, count=count) for ip_hash, count in sorted_rows]


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
    include_demo: bool,
    limit: int = 10,
) -> list[MapDrilldownPath]:
    normalized_category = _normalize_category(category)
    if normalized_category not in {None, SecurityCategoryEnum.THREAT.value}:
        return []
    if website_id or env_id:
        return []
    path_counts: dict[str, int] = {}

    alert_query = (
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
    if hasattr(IPEnrichment, "is_demo") and not include_demo:
        alert_query = alert_query.filter(IPEnrichment.is_demo.is_(False))
    alert_query = _apply_time_filters(alert_query, Alert.timestamp, from_ts, to_ts)
    if bucket_start:
        alert_query = alert_query.filter(
            Alert.timestamp >= bucket_start,
            Alert.timestamp < bucket_start + timedelta(hours=1),
        )
    alert_query = _apply_enrichment_location_filter(
        alert_query,
        country_code=country_code,
        lat=lat,
        lon=lon,
        radius_km=radius_km,
    )
    for row in alert_query.group_by(Alert.request_path).all():
        if not row.path:
            continue
        path_counts[row.path] = path_counts.get(row.path, 0) + int(row.count or 0)

    time_col = func.coalesce(SecurityEvent.event_ts, SecurityEvent.created_at)
    sec_query = (
        db.query(SecurityEvent.request_path.label("path"), func.count().label("count"))
        .join(
            IPEnrichment,
            and_(SecurityEvent.tenant_id == IPEnrichment.tenant_id, SecurityEvent.ip_hash == IPEnrichment.ip_hash),
        )
        .filter(
            SecurityEvent.tenant_id == tenant_id,
            SecurityEvent.category == SecurityCategoryEnum.THREAT.value,
            SecurityEvent.request_path.isnot(None),
            SecurityEvent.ip_hash.isnot(None),
            IPEnrichment.lookup_status == "ok",
        )
    )
    if not include_demo:
        sec_query = sec_query.filter(SecurityEvent.is_demo.is_(False), IPEnrichment.is_demo.is_(False))
    sec_query = _apply_time_filters(sec_query, time_col, from_ts, to_ts)
    if bucket_start:
        sec_query = sec_query.filter(
            time_col >= bucket_start,
            time_col < bucket_start + timedelta(hours=1),
        )
    sec_query = _apply_enrichment_location_filter(
        sec_query,
        country_code=country_code,
        lat=lat,
        lon=lon,
        radius_km=radius_km,
    )
    for row in sec_query.group_by(SecurityEvent.request_path).all():
        if not row.path:
            continue
        path_counts[row.path] = path_counts.get(row.path, 0) + int(row.count or 0)

    sorted_rows = sorted(path_counts.items(), key=lambda item: item[1], reverse=True)[:limit]
    return [MapDrilldownPath(path=path, count=count) for path, count in sorted_rows if path]


@router.get("/summary", response_model=MapSummaryResponse)
def map_summary(
    from_ts: datetime | None = Query(None, alias="from"),
    to_ts: datetime | None = Query(None, alias="to"),
    website_id: int | None = None,
    env_id: int | None = None,
    category: str | None = None,
    severity: str | None = None,
    include_demo: bool = Query(False, alias="include_demo"),
    db: Session = Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.VIEWER], user_resolver=get_current_user)),
):
    tenant = _resolve_tenant(db, ctx.tenant_id)
    tenant_id = tenant.id
    include_demo = bool(include_demo and tenant.is_demo_mode and not settings.LAUNCH_MODE)
    category = _normalize_category(category)
    entitlements = resolve_effective_entitlements(db, tenant_id)
    features = entitlements.get("features", {})
    limits = entitlements.get("limits", {})
    geo_enabled = bool(features.get("geo_map"))
    max_geo_days = _coerce_positive_int(limits.get("geo_history_days"))
    if not geo_enabled:
        max_geo_days = 1
    clamp_limits = dict(limits)
    clamp_limits["geo_history_days"] = max_geo_days
    clamp_result = clamp_range({"limits": clamp_limits}, "geo_history_days", from_ts, to_ts)
    from_ts, to_ts = clamp_result.from_ts, clamp_result.to_ts
    if bucket_start:
        bucket_start = _normalize_ts(bucket_start)

    with trace_span(
        "map.summary",
        tenant_id=tenant_id,
        website_id=website_id,
        environment_id=env_id,
        category=category,
    ):
        cache_key = build_cache_key(
            "map.summary",
            tenant_id=tenant_id,
            db_scope=db_scope_id(db),
            filters={
                "from": from_ts,
                "to": to_ts,
                "website_id": website_id,
                "env_id": env_id,
                "category": category,
                "severity": severity,
                "geo_enabled": geo_enabled,
                "include_demo": include_demo,
                "plan_key": entitlements.get("plan_key"),
            },
        )
        cached = cache_get(cache_key, cache_name="map.summary")
        if cached is not None:
            return MapSummaryResponse(**cached)

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
        if not include_demo:
            query = query.filter(GeoEventAgg.is_demo.is_(False))
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

        payload = MapSummaryResponse(items=items)
        cache_set(
            cache_key,
            payload,
            ttl=settings.CACHE_TTL_MAP_SUMMARY,
            cache_name="map.summary",
        )
        return payload


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
    include_demo: bool = Query(False, alias="include_demo"),
    db: Session = Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.VIEWER], user_resolver=get_current_user)),
):
    tenant = _resolve_tenant(db, ctx.tenant_id)
    tenant_id = tenant.id
    include_demo = bool(include_demo and tenant.is_demo_mode and not settings.LAUNCH_MODE)
    category = _normalize_category(category)
    entitlements = resolve_effective_entitlements(db, tenant_id)
    features = entitlements.get("features", {})
    limits = entitlements.get("limits", {})
    geo_enabled = bool(features.get("geo_map"))
    max_geo_days = _coerce_positive_int(limits.get("geo_history_days"))
    if not geo_enabled:
        max_geo_days = 1
    clamp_limits = dict(limits)
    clamp_limits["geo_history_days"] = max_geo_days
    clamp_result = clamp_range({"limits": clamp_limits}, "geo_history_days", from_ts, to_ts)
    from_ts, to_ts = clamp_result.from_ts, clamp_result.to_ts

    with trace_span(
        "map.drilldown",
        tenant_id=tenant_id,
        website_id=website_id,
        environment_id=env_id,
        category=category,
    ):
        cache_key = build_cache_key(
            "map.drilldown",
            tenant_id=tenant_id,
            db_scope=db_scope_id(db),
            filters={
                "from": from_ts,
                "to": to_ts,
                "website_id": website_id,
                "env_id": env_id,
                "category": category,
                "severity": severity,
                "bucket_start": bucket_start,
                "country_code": country_code,
                "lat": lat,
                "lon": lon,
                "radius_km": radius_km,
                "geo_enabled": geo_enabled,
                "include_demo": include_demo,
                "plan_key": entitlements.get("plan_key"),
            },
        )
        cached = cache_get(cache_key, cache_name="map.drilldown")
        if cached is not None:
            return MapDrilldownResponse(**cached)

        base_query = db.query(GeoEventAgg).filter(GeoEventAgg.tenant_id == tenant_id)
        if not include_demo:
            base_query = base_query.filter(GeoEventAgg.is_demo.is_(False))
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
                include_demo=include_demo,
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
                include_demo=include_demo,
            )

        payload = MapDrilldownResponse(
            countries=countries,
            cities=cities,
            asns=asns,
            ip_hashes=ip_hashes,
            paths=paths,
        )
        cache_set(
            cache_key,
            payload,
            ttl=settings.CACHE_TTL_MAP_DRILLDOWN,
            cache_name="map.drilldown",
        )
        return payload
