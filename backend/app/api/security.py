
# This module centralizes two related ideas: (1) a global on/off flag
# that lets us simulate “defenses enabled vs disabled,” and (2) a simple
# rotating “chain token” mechanism that forces each protected request to
# present the current token value, which rotates after every valid use.
# It’s intentionally lightweight so demos can illustrate the concepts
# without dragging in heavyweight, external dependencies.

from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Depends, Query, status
import hashlib
import secrets

from app.core.config import settings
from app.api.dependencies import require_role, get_current_user
from app.core.db import get_db
from app.core.privacy import mask_ip
from app.core.entitlements import resolve_effective_entitlements
from app.entitlements.enforcement import clamp_range
from app.crud.tenants import get_tenant_by_id, get_tenant_by_slug
from app.models.alerts import Alert
from app.models.audit_logs import AuditLog
from app.models.enums import RoleEnum
from app.models.events import Event
from app.models.security_events import SecurityEvent
from app.schemas.security import (
    SecurityIpBreakdown,
    SecurityIpSummary,
    SecurityIpSummaryResponse,
    SecurityLocationSummary,
    SecurityLocationSummaryResponse,
)
from app.schemas.security_events import SecurityEventListItem, SecurityEventListResponse
from app.security.taxonomy import SecurityCategoryEnum, SeverityEnum
from app.tenancy.dependencies import require_role_in_tenant
from sqlalchemy import func

# ------------------------------------------------------------
# SECURITY_ENABLED is a single switch that controls whether the
# stuffing protections are enforced. In demos, being able to flip
# this at runtime is super helpful: you can show the exact same flow
# with defenses off (attacks succeed) and on (attacks blocked),
# all without restarting the app or changing code paths.
SECURITY_ENABLED = True

# ------------------------------------------------------------
# CURRENT_CHAIN stores the “one-time” chain value expected from
# the next protected request. Think of it like a running secret:
# clients must present the current token, and on success we rotate
# it forward. That rotation makes replayed or stale requests easy
# to detect and reject on the spot.
CURRENT_CHAIN = None


# ------------------------------------------------------------
# _hash(value) is a tiny helper that wraps SHA-256 for readability.
# Using a fixed, strong hash keeps the chain derivation simple while
# still being deterministic and tamper-evident. The seed input mixes
# in a secret so raw token material is never stored or compared.
def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


# ------------------------------------------------------------
# _new_chain(prev) derives the next chain value. We combine either
# the previous chain (if present) or a stable app secret with some
# fresh randomness. That gives us forward movement + unpredictability,
# so each call gets a new token and replay defense comes for free.
def _new_chain(prev: str | None = None) -> str:
    """Return a new chain value derived from ``prev`` and randomness."""
    seed = prev or settings.SECRET_KEY
    return _hash(seed + secrets.token_hex(8))


# ------------------------------------------------------------
# init_chain() is called at startup (and when security flips on)
# so the first request has a valid chain to present. I keep it
# tiny and explicit to avoid any “None” surprises, and so that
# the rotation logic stays straightforward across the lifetime.
def init_chain() -> None:
    """Initialise the global chain value."""
    global CURRENT_CHAIN
    CURRENT_CHAIN = _new_chain()


# ------------------------------------------------------------
# rotate_chain() advances the chain state after a successful check.
# Rotating ensures the same token can’t be used twice, which gives
# us a clean, easy replay-protection story even without timestamps
# or complex server-side state machines. One in, one out—done.
def rotate_chain() -> None:
    """Advance the chain to the next value."""
    global CURRENT_CHAIN
    CURRENT_CHAIN = _new_chain(CURRENT_CHAIN)


# ------------------------------------------------------------
# verify_chain(token) is the gatekeeper. It compares the presented
# token to the expected CURRENT_CHAIN. If they don’t match, we reject
# with a 401 and never rotate. If they do match, we rotate immediately
# so the token cannot be replayed. Simple, fast, and state-light.
def verify_chain(token: str | None) -> None:
    """Validate ``token`` matches the current chain and rotate."""
    if token != CURRENT_CHAIN:
        raise HTTPException(status_code=401, detail="Invalid chain token")
    rotate_chain()


# ------------------------------------------------------------
# Initialize the chain as soon as this module is imported, which
# happens when the app starts. That way, protected routes that check
# the chain have a valid initial value without any explicit boot step.
# Re-initialization also happens when SECURITY_ENABLED flips to True.
init_chain()

# ------------------------------------------------------------
# Router configuration: all endpoints live under /api/security
# and get tagged as “security” in the docs. Keeping these controls
# in a dedicated router makes them easy to find and to lock behind
# admin-only authorization requirements.
router = APIRouter(prefix="/security", tags=["security"])

GRANULARITY_LEVELS = {"country": 0, "city": 1, "asn": 2}


def _resolve_tenant_id(db, tenant_hint: str) -> int:
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


def _apply_time_filters(query, model, from_ts: datetime | None, to_ts: datetime | None):
    if from_ts:
        query = query.filter(model.timestamp >= from_ts)
    if to_ts:
        query = query.filter(model.timestamp <= to_ts)
    return query


def _coerce_positive_int(value) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _normalize_category(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    try:
        return SecurityCategoryEnum(normalized).value
    except ValueError:
        return None


def _normalize_severity(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    try:
        return SeverityEnum(normalized).value
    except ValueError:
        return None


def _mask_ip_hash(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 12:
        return value
    return f"{value[:6]}...{value[-4:]}"


def _apply_granularity(payload: dict, granularity_rank: int) -> dict:
    data = dict(payload)
    if granularity_rank < GRANULARITY_LEVELS["asn"]:
        data["asn_number"] = None
        data["asn_org"] = None
        data["is_datacenter"] = None
    if granularity_rank < GRANULARITY_LEVELS["city"]:
        data["region"] = None
        data["city"] = None
        data["latitude"] = None
        data["longitude"] = None
    return data


def _query_ip_stats(db, model, tenant_id: int, from_ts: datetime | None, to_ts: datetime | None):
    query = (
        db.query(
            model.ip_hash.label("ip_hash"),
            func.count().label("count"),
            func.max(model.timestamp).label("last_seen"),
            func.max(model.client_ip).label("client_ip"),
        )
        .filter(
            model.tenant_id == tenant_id,
            model.ip_hash.isnot(None),
            model.ip_hash != "",
        )
        .group_by(model.ip_hash)
    )
    return _apply_time_filters(query, model, from_ts, to_ts).all()


def _query_location_stats(db, model, tenant_id: int, from_ts: datetime | None, to_ts: datetime | None):
    query = (
        db.query(
            model.country_code.label("country_code"),
            func.count().label("count"),
            func.max(model.timestamp).label("last_seen"),
        )
        .filter(
            model.tenant_id == tenant_id,
            model.country_code.isnot(None),
            model.country_code != "",
        )
        .group_by(model.country_code)
    )
    return _apply_time_filters(query, model, from_ts, to_ts).all()


# ------------------------------------------------------------
# GET /api/security/
# Returns the current “defenses on/off” state. I lock this behind
# an admin role because even read access can leak implementation
# details. The payload is intentionally small: a single boolean
# that the UI can turn into a neat toggle.
@router.get("/")
def get_security(_user=Depends(require_role("admin"))):
    """Return current security enforcement state."""
    return {"enabled": SECURITY_ENABLED}


# ------------------------------------------------------------
# GET /api/security/chain
# Exposes the current chain value to admins only. In the demo flow,
# the test client or simulator fetches this and then presents it in
# the X-Chain-Password header. Because we rotate on every successful
# verification, this value changes after each valid protected call.
@router.get("/chain")
def get_chain(_user=Depends(require_role("admin"))):
    """Retrieve the current chain value."""
    return {"chain": CURRENT_CHAIN}


# ------------------------------------------------------------
# POST /api/security/
# Allows an admin to toggle SECURITY_ENABLED at runtime. When enabling,
# we also re-initialize the chain so a fresh, unpredictable value kicks
# off the next cycle. When disabling, we clear the chain so no one can
# accidentally rely on it while protections are off.
@router.post("/")
def set_security(payload: dict, _user=Depends(require_role("admin"))):
    """Update security enforcement state."""
    enabled = payload.get("enabled")
    if not isinstance(enabled, bool):
        raise HTTPException(status_code=422, detail="'enabled' boolean required")
    global SECURITY_ENABLED
    SECURITY_ENABLED = enabled
    if enabled:
        init_chain()
    else:
        # Clear chain when security disabled to avoid stale expectations.
        global CURRENT_CHAIN
        CURRENT_CHAIN = None
    return {"enabled": SECURITY_ENABLED}


@router.get("/ips", response_model=SecurityIpSummaryResponse)
def list_security_ips(
    from_ts: datetime | None = Query(None, alias="from"),
    to_ts: datetime | None = Query(None, alias="to"),
    severity: str | None = None,
    website_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    include_raw_ip: bool = False,
    db=Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.VIEWER], user_resolver=get_current_user)),
):
    # severity and website_id are reserved for future filtering.
    _ = severity, website_id
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
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
    ip_stats = {}

    def _merge(rows, source: str):
        for row in rows:
            ip_hash = row.ip_hash
            if not ip_hash:
                continue
            entry = ip_stats.setdefault(
                ip_hash,
                {
                    "total_count": 0,
                    "last_seen": None,
                    "client_ip": None,
                    "breakdown": {"event": 0, "alert": 0, "audit": 0},
                },
            )
            entry["total_count"] += int(row.count or 0)
            entry["breakdown"][source] += int(row.count or 0)
            if row.last_seen and (entry["last_seen"] is None or row.last_seen > entry["last_seen"]):
                entry["last_seen"] = row.last_seen
            if not entry["client_ip"] and row.client_ip:
                entry["client_ip"] = row.client_ip

    _merge(_query_ip_stats(db, Event, tenant_id, from_ts, to_ts), "event")
    _merge(_query_ip_stats(db, Alert, tenant_id, from_ts, to_ts), "alert")
    _merge(_query_ip_stats(db, AuditLog, tenant_id, from_ts, to_ts), "audit")

    allow_raw_ip = (
        include_raw_ip
        and geo_enabled
        and settings.ALLOW_RAW_IP_SECURITY_ENDPOINTS
        and ctx.role in {RoleEnum.OWNER, RoleEnum.ADMIN}
    )
    raw_ip_cutoff = None
    if allow_raw_ip:
        effective_raw_days = _coerce_positive_int(limits.get("raw_ip_retention_days"))
        if effective_raw_days is None:
            allow_raw_ip = False
        else:
            raw_ip_cutoff = datetime.utcnow() - timedelta(days=effective_raw_days)

    items: list[SecurityIpSummary] = []
    for ip_hash, entry in ip_stats.items():
        last_seen = entry["last_seen"]
        if last_seen is None:
            continue
        client_ip = entry["client_ip"]
        masked = None
        if client_ip:
            try:
                masked = mask_ip(client_ip)
            except ValueError:
                masked = None
        raw_ip = None
        if allow_raw_ip and client_ip and raw_ip_cutoff and last_seen >= raw_ip_cutoff:
            raw_ip = client_ip
        items.append(
            SecurityIpSummary(
                ip_hash=ip_hash,
                total_count=entry["total_count"],
                last_seen=last_seen,
                breakdown=SecurityIpBreakdown(**entry["breakdown"]),
                masked_ip=masked,
                client_ip=raw_ip,
            )
        )

    items.sort(key=lambda item: (item.total_count, item.last_seen), reverse=True)
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return SecurityIpSummaryResponse(
        items=items[start:end],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/locations", response_model=SecurityLocationSummaryResponse)
def list_security_locations(
    from_ts: datetime | None = Query(None, alias="from"),
    to_ts: datetime | None = Query(None, alias="to"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db=Depends(get_db),
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
    clamp_limits = dict(limits)
    clamp_limits["geo_history_days"] = max_geo_days
    clamp_result = clamp_range({"limits": clamp_limits}, "geo_history_days", from_ts, to_ts)
    from_ts, to_ts = clamp_result.from_ts, clamp_result.to_ts
    location_stats = {}

    def _merge(rows):
        for row in rows:
            code = row.country_code
            if not code:
                continue
            entry = location_stats.setdefault(
                code,
                {"count": 0, "last_seen": None},
            )
            entry["count"] += int(row.count or 0)
            if row.last_seen and (entry["last_seen"] is None or row.last_seen > entry["last_seen"]):
                entry["last_seen"] = row.last_seen

    _merge(_query_location_stats(db, Event, tenant_id, from_ts, to_ts))
    _merge(_query_location_stats(db, Alert, tenant_id, from_ts, to_ts))
    _merge(_query_location_stats(db, AuditLog, tenant_id, from_ts, to_ts))

    items: list[SecurityLocationSummary] = []
    for code, entry in location_stats.items():
        if entry["last_seen"] is None:
            continue
        items.append(
            SecurityLocationSummary(
                country_code=code,
                count=entry["count"],
                last_seen=entry["last_seen"],
            )
        )

    items.sort(key=lambda item: (item.count, item.last_seen), reverse=True)
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return SecurityLocationSummaryResponse(
        items=items[start:end],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/events", response_model=SecurityEventListResponse)
def list_security_events(
    from_ts: datetime | None = Query(None, alias="from"),
    to_ts: datetime | None = Query(None, alias="to"),
    category: str | None = None,
    severity: str | None = None,
    website_id: int | None = None,
    env_id: int | None = None,
    ip_hash: str | None = None,
    country_code: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db=Depends(get_db),
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
    clamp_limits = dict(limits)
    clamp_limits["geo_history_days"] = max_geo_days
    clamp_result = clamp_range({"limits": clamp_limits}, "geo_history_days", from_ts, to_ts)
    from_ts, to_ts = clamp_result.from_ts, clamp_result.to_ts

    normalized_category = _normalize_category(category)
    normalized_severity = _normalize_severity(severity)
    event_time_expr = func.coalesce(SecurityEvent.event_ts, SecurityEvent.created_at)

    query = db.query(SecurityEvent).filter(SecurityEvent.tenant_id == tenant_id)
    if normalized_category:
        query = query.filter(SecurityEvent.category == normalized_category)
    if normalized_severity:
        query = query.filter(SecurityEvent.severity == normalized_severity)
    if website_id:
        query = query.filter(SecurityEvent.website_id == website_id)
    if env_id:
        query = query.filter(SecurityEvent.environment_id == env_id)
    if ip_hash:
        query = query.filter(SecurityEvent.ip_hash == ip_hash)
    if country_code:
        query = query.filter(SecurityEvent.country_code == country_code.upper())
    if from_ts:
        query = query.filter(event_time_expr >= from_ts)
    if to_ts:
        query = query.filter(event_time_expr <= to_ts)

    total = query.count()
    rows = (
        query.order_by(event_time_expr.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    granularity_value = str(limits.get("geo_granularity") or "").lower()
    granularity_rank = GRANULARITY_LEVELS.get(granularity_value, GRANULARITY_LEVELS["city"])
    if not geo_enabled:
        granularity_rank = GRANULARITY_LEVELS["country"]

    items: list[SecurityEventListItem] = []
    for row in rows:
        payload = _apply_granularity(
            {
                "id": row.id,
                "event_ts": row.event_ts,
                "created_at": row.created_at,
                "event_type": row.event_type,
                "category": row.category,
                "severity": row.severity,
                "request_path": row.request_path,
                "status_code": row.status_code,
                "ip_hash": _mask_ip_hash(row.ip_hash),
                "website_id": row.website_id,
                "environment_id": row.environment_id,
                "country_code": row.country_code,
                "region": row.region,
                "city": row.city,
                "latitude": row.latitude,
                "longitude": row.longitude,
                "asn_number": row.asn_number,
                "asn_org": row.asn_org,
                "is_datacenter": row.is_datacenter,
            },
            granularity_rank,
        )
        items.append(SecurityEventListItem(**payload))

    return SecurityEventListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )
