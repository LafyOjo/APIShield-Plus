from __future__ import annotations

from datetime import datetime
import logging
from ipaddress import ip_address
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.entitlements import resolve_effective_entitlements
from app.core.keys import verify_secret
from app.core.metrics import record_ingest_event, record_ingest_latency
from app.core.privacy import hash_ip
from app.core.rate_limit import allow, is_banned, register_invalid_attempt
from app.core.tracing import trace_span
from app.crud.api_keys import get_api_key_by_public_key, mark_api_key_used
from app.geo.enrichment import mark_ip_seen
from app.models.api_keys import APIKey
from app.models.enums import WebsiteStatusEnum
from app.models.security_events import SecurityEvent
from app.models.website_environments import WebsiteEnvironment
from app.models.websites import Website
from app.schemas.ingest_security import IngestSecurityEvent, IngestSecurityResponse
from app.security.taxonomy import get_category


router = APIRouter(prefix="/ingest", tags=["ingest"])
logger = logging.getLogger(__name__)


def _extract_api_secret(request: Request) -> str | None:
    for header in ("X-Api-Secret", "X-API-Secret"):
        value = request.headers.get(header)
        if value:
            return value.strip()
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return None


def _extract_public_key(request: Request) -> str | None:
    return request.headers.get("X-Api-Key") or request.headers.get("X-API-Key")


def _fallback_client_ip(request: Request) -> str | None:
    if request is None:
        return None
    for header in ("X-Forwarded-For", "X-Real-IP"):
        raw = request.headers.get(header)
        if not raw:
            continue
        candidate = raw.split(",")[0].strip()
        try:
            return str(ip_address(candidate))
        except ValueError:
            continue
    return None


def _find_api_key_by_secret(db: Session, secret: str) -> APIKey | None:
    if not secret or not secret.startswith("sk_"):
        return None
    keys = db.query(APIKey).all()
    for api_key in keys:
        if verify_secret(secret, api_key.secret_hash):
            return api_key
    return None


def _coerce_positive_int(value, default: int) -> int:
    if value is None or isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _raise_rate_limit(retry_after: int, detail: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=detail,
        headers={"Retry-After": str(max(1, retry_after))},
    )


def _enforce_body_limit(request: Request) -> None:
    max_bytes = settings.INGEST_MAX_BODY_BYTES
    content_length = request.headers.get("Content-Length")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Payload too large",
                )
        except ValueError:
            pass


def _resolve_api_key(db: Session, secret: str, client_ip: str | None) -> APIKey:
    api_key = _find_api_key_by_secret(db, secret)
    if not api_key or api_key.revoked_at is not None or api_key.status == "revoked":
        ban_for = register_invalid_attempt(
            client_ip,
            threshold=settings.INGEST_INVALID_BAN_THRESHOLD,
            ban_seconds=settings.INGEST_BAN_SECONDS,
            window_seconds=settings.INGEST_INVALID_WINDOW_SECONDS,
        )
        if ban_for:
            _raise_rate_limit(ban_for, "Too many invalid requests")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API secret")
    return api_key


def _resolve_public_key(db: Session, public_key: str, client_ip: str | None) -> APIKey:
    api_key = get_api_key_by_public_key(db, public_key)
    if not api_key or api_key.revoked_at is not None or api_key.status == "revoked":
        ban_for = register_invalid_attempt(
            client_ip,
            threshold=settings.INGEST_INVALID_BAN_THRESHOLD,
            ban_seconds=settings.INGEST_BAN_SECONDS,
            window_seconds=settings.INGEST_INVALID_WINDOW_SECONDS,
        )
        if ban_for:
            _raise_rate_limit(ban_for, "Too many invalid requests")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    return api_key


def _resolve_site_env(db: Session, api_key: APIKey) -> tuple[Website, WebsiteEnvironment]:
    website = (
        db.query(Website)
        .filter(
            Website.id == api_key.website_id,
            Website.tenant_id == api_key.tenant_id,
        )
        .first()
    )
    if not website or website.deleted_at is not None or website.status != WebsiteStatusEnum.ACTIVE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Website not found")
    environment = (
        db.query(WebsiteEnvironment)
        .filter(
            WebsiteEnvironment.id == api_key.environment_id,
            WebsiteEnvironment.website_id == website.id,
        )
        .first()
    )
    if not environment or environment.status != "active":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found")
    return website, environment


def _apply_rate_limits(
    db: Session,
    api_key: APIKey,
    client_ip: str | None,
    ip_hash: str | None,
) -> None:
    entitlements = resolve_effective_entitlements(db, api_key.tenant_id)
    limits = entitlements.get("limits", {}) if entitlements else {}
    rpm_limit = _coerce_positive_int(limits.get("ingest_rpm"), settings.INGEST_DEFAULT_RPM)
    burst_limit = _coerce_positive_int(limits.get("ingest_burst"), settings.INGEST_DEFAULT_BURST)

    key_allowed, key_retry = allow(
        f"ingest:security:key:{api_key.public_key}",
        capacity=burst_limit,
        refill_rate_per_sec=rpm_limit / 60.0,
    )
    if not key_allowed:
        _raise_rate_limit(key_retry, "Rate limit exceeded")

    if ip_hash:
        ip_allowed, ip_retry = allow(
            f"ingest:security:ip:{ip_hash}",
            capacity=settings.INGEST_IP_BURST,
            refill_rate_per_sec=settings.INGEST_IP_RPM / 60.0,
        )
        if not ip_allowed:
            _raise_rate_limit(ip_retry, "Rate limit exceeded")
    elif client_ip:
        ip_allowed, ip_retry = allow(
            f"ingest:security:ip:{client_ip}",
            capacity=settings.INGEST_IP_BURST,
            refill_rate_per_sec=settings.INGEST_IP_RPM / 60.0,
        )
        if not ip_allowed:
            _raise_rate_limit(ip_retry, "Rate limit exceeded")


def _record_security_event(
    db: Session,
    *,
    api_key: APIKey,
    payload: IngestSecurityEvent,
    source: str,
    client_ip: str | None,
    user_agent: str | None,
) -> None:
    ip_hash = None
    if client_ip:
        try:
            ip_hash = hash_ip(api_key.tenant_id, client_ip)
        except ValueError:
            ip_hash = None

    if ip_hash:
        try:
            mark_ip_seen(db, api_key.tenant_id, ip_hash)
        except Exception:
            logger.exception("Failed to record geo enrichment seed")

    _apply_rate_limits(db, api_key, client_ip, ip_hash)

    category = get_category(payload.event_type).value
    resolved_source = payload.source or source

    db.add(
        SecurityEvent(
            tenant_id=api_key.tenant_id,
            website_id=api_key.website_id,
            environment_id=api_key.environment_id,
            created_at=datetime.utcnow(),
            event_ts=payload.ts,
            category=category,
            event_type=payload.event_type,
            severity=payload.severity,
            source=resolved_source,
            request_path=payload.request_path,
            method=payload.method,
            status_code=payload.status_code,
            user_identifier=payload.user_identifier,
            session_id=payload.session_id,
            client_ip=client_ip,
            user_agent=user_agent,
            ip_hash=ip_hash,
            meta=payload.meta,
        )
    )
    db.commit()
    mark_api_key_used(db, api_key.public_key)


@router.post("/security", response_model=IngestSecurityResponse)
async def ingest_security_event(
    payload: IngestSecurityEvent,
    request: Request,
    db: Session = Depends(get_db),
):
    start_time = monotonic()
    ingest_type = "security"
    _enforce_body_limit(request)
    client_ip = getattr(request.state, "client_ip", None) or _fallback_client_ip(request)
    banned, retry_after = is_banned(client_ip)
    if banned:
        _raise_rate_limit(retry_after, "Too many invalid requests")

    secret = _extract_api_secret(request)
    if not secret:
        ban_for = register_invalid_attempt(
            client_ip,
            threshold=settings.INGEST_INVALID_BAN_THRESHOLD,
            ban_seconds=settings.INGEST_BAN_SECONDS,
            window_seconds=settings.INGEST_INVALID_WINDOW_SECONDS,
        )
        if ban_for:
            _raise_rate_limit(ban_for, "Too many invalid requests")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API secret")

    api_key = _resolve_api_key(db, secret, client_ip)
    _resolve_site_env(db, api_key)
    user_agent = getattr(request.state, "user_agent", None)
    with trace_span(
        "ingest.security",
        tenant_id=api_key.tenant_id,
        website_id=api_key.website_id,
        environment_id=api_key.environment_id,
        event_type=payload.event_type,
    ):
        _record_security_event(
            db,
            api_key=api_key,
            payload=payload,
            source="server",
            client_ip=client_ip,
            user_agent=user_agent,
        )
    record_ingest_event(
        tenant_id=api_key.tenant_id,
        website_id=api_key.website_id,
        environment_id=api_key.environment_id,
        event_type=payload.event_type,
        ingest_type=ingest_type,
    )
    record_ingest_latency(
        ingest_type=ingest_type,
        duration_ms=(monotonic() - start_time) * 1000.0,
    )
    return IngestSecurityResponse(ok=True, received_at=datetime.utcnow())


@router.post("/integrity", response_model=IngestSecurityResponse)
async def ingest_integrity_event(
    payload: IngestSecurityEvent,
    request: Request,
    db: Session = Depends(get_db),
):
    start_time = monotonic()
    ingest_type = "integrity"
    _enforce_body_limit(request)
    client_ip = getattr(request.state, "client_ip", None) or _fallback_client_ip(request)
    banned, retry_after = is_banned(client_ip)
    if banned:
        _raise_rate_limit(retry_after, "Too many invalid requests")

    public_key = _extract_public_key(request)
    if not public_key:
        ban_for = register_invalid_attempt(
            client_ip,
            threshold=settings.INGEST_INVALID_BAN_THRESHOLD,
            ban_seconds=settings.INGEST_BAN_SECONDS,
            window_seconds=settings.INGEST_INVALID_WINDOW_SECONDS,
        )
        if ban_for:
            _raise_rate_limit(ban_for, "Too many invalid requests")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API key")

    api_key = _resolve_public_key(db, public_key, client_ip)
    _resolve_site_env(db, api_key)
    user_agent = getattr(request.state, "user_agent", None)
    with trace_span(
        "ingest.integrity",
        tenant_id=api_key.tenant_id,
        website_id=api_key.website_id,
        environment_id=api_key.environment_id,
        event_type=payload.event_type,
    ):
        _record_security_event(
            db,
            api_key=api_key,
            payload=payload,
            source="browser",
            client_ip=client_ip,
            user_agent=user_agent,
        )
    record_ingest_event(
        tenant_id=api_key.tenant_id,
        website_id=api_key.website_id,
        environment_id=api_key.environment_id,
        event_type=payload.event_type,
        ingest_type=ingest_type,
    )
    record_ingest_latency(
        ingest_type=ingest_type,
        duration_ms=(monotonic() - start_time) * 1000.0,
    )
    return IngestSecurityResponse(ok=True, received_at=datetime.utcnow())
