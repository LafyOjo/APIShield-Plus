from __future__ import annotations

from datetime import datetime
import json
import logging
from ipaddress import ip_address
from time import monotonic
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.anomaly import AnomalyContext, evaluate_event_for_anomaly
from app.core.config import settings
from app.core.db import get_db
from app.core.entitlements import resolve_effective_entitlements
from app.core.event_types import normalize_path
from app.core.metrics import record_ingest_event, record_ingest_latency
from app.core.onboarding_emails import queue_first_event_email
from app.core.usage import get_or_create_current_period_usage, increment_storage
from app.entitlements.enforcement import assert_limit
from app.core.privacy import hash_ip
from app.core.rate_limit import allow, is_banned, register_abuse_attempt, register_invalid_attempt
from app.core.tracing import trace_span
from app.core.usage import increment_events
from app.core.utils.domain import normalize_domain
from app.crud.api_keys import get_api_key_by_public_key, mark_api_key_used
from app.crud.behaviour_events import create_behaviour_event, get_behaviour_event_by_event_id
from app.crud.behaviour_sessions import upsert_behaviour_session
from app.geo.enrichment import mark_ip_seen
from app.models.anomaly_signals import AnomalySignalEvent
from app.models.enums import WebsiteStatusEnum
from app.models.website_environments import WebsiteEnvironment
from app.models.websites import Website
from app.crud.website_stack_profiles import apply_stack_detection
from app.schemas.ingest import IngestBrowserEvent, IngestBrowserResponse


router = APIRouter(prefix="/ingest", tags=["ingest"])
logger = logging.getLogger(__name__)


def _extract_public_key(request: Request) -> str | None:
    return request.headers.get("X-Api-Key") or request.headers.get("X-API-Key")


def _matches_domain(event_url: str, website_domain: str) -> bool:
    parsed = urlsplit(event_url)
    host = parsed.hostname
    if not host:
        return False
    host = host.lower()
    try:
        normalized = normalize_domain(website_domain)
    except ValueError:
        return False
    return host == normalized or host.endswith(f".{normalized}")


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


def _coerce_positive_int(value, default: int) -> int:
    if value is None or isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


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


def _raise_rate_limit(retry_after: int, detail: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=detail,
        headers={"Retry-After": str(max(1, retry_after))},
    )


def _estimate_payload_bytes(payload: IngestBrowserEvent) -> int:
    try:
        data = payload.model_dump(mode="json")
    except TypeError:
        data = payload.model_dump()
    except AttributeError:
        data = payload.dict()
    return len(
        json.dumps(data, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    )


@router.post("/browser", response_model=IngestBrowserResponse)
async def ingest_browser_event(
    payload: IngestBrowserEvent,
    request: Request,
    db: Session = Depends(get_db),
):
    start_time = monotonic()
    ingest_type = "browser"
    _enforce_body_limit(request)
    body = await request.body()
    if body and len(body) > settings.INGEST_MAX_BODY_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Payload too large",
        )

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

    if not _matches_domain(payload.url, website.domain):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Domain mismatch")

    request_id = getattr(request.state, "request_id", None)
    ip_hash = None
    if client_ip:
        try:
            ip_hash = hash_ip(api_key.tenant_id, client_ip)
        except ValueError:
            ip_hash = None
    if ip_hash:
        banned, retry_after = is_banned(f"iphash:{ip_hash}")
        if banned:
            _raise_rate_limit(retry_after, "Too many abusive requests")
    if ip_hash:
        try:
            mark_ip_seen(db, api_key.tenant_id, ip_hash)
        except Exception:
            logger.exception("Failed to record geo enrichment seed")
    user_agent = getattr(request.state, "user_agent", None)
    event_path = payload.path
    if not event_path:
        event_path = normalize_path(urlsplit(payload.url).path or "/")

    entitlements = resolve_effective_entitlements(db, api_key.tenant_id)
    limits = entitlements.get("limits", {})
    rpm_limit = _coerce_positive_int(limits.get("ingest_rpm"), settings.INGEST_DEFAULT_RPM)
    burst_limit = _coerce_positive_int(limits.get("ingest_burst"), settings.INGEST_DEFAULT_BURST)
    key_allowed, key_retry = allow(
        f"ingest:key:{api_key.public_key}",
        capacity=burst_limit,
        refill_rate_per_sec=rpm_limit / 60.0,
    )
    if not key_allowed:
        _raise_rate_limit(key_retry, "Rate limit exceeded")

    if ip_hash:
        ip_allowed, ip_retry = allow(
            f"ingest:ip:{ip_hash}",
            capacity=settings.INGEST_IP_BURST,
            refill_rate_per_sec=settings.INGEST_IP_RPM / 60.0,
        )
        if not ip_allowed:
            ban_for = register_abuse_attempt(
                f"iphash:{ip_hash}",
                threshold=settings.INGEST_ABUSE_BAN_THRESHOLD,
                ban_seconds=settings.INGEST_ABUSE_BAN_SECONDS,
                window_seconds=settings.INGEST_ABUSE_WINDOW_SECONDS,
            )
            if ban_for:
                _raise_rate_limit(ban_for, "Too many abusive requests")
            _raise_rate_limit(ip_retry, "Rate limit exceeded")

    existing_event = get_behaviour_event_by_event_id(
        db,
        tenant_id=api_key.tenant_id,
        environment_id=environment.id,
        event_id=payload.event_id,
    )
    if existing_event:
        mark_api_key_used(db, api_key.public_key)
        record_ingest_event(
            tenant_id=api_key.tenant_id,
            website_id=website.id,
            environment_id=environment.id,
            event_type=payload.type,
            ingest_type=ingest_type,
        )
        record_ingest_latency(
            ingest_type=ingest_type,
            duration_ms=(monotonic() - start_time) * 1000.0,
        )
        return IngestBrowserResponse(
            ok=True,
            received_at=datetime.utcnow(),
            request_id=request_id,
            deduped=True,
        )

    payload_bytes = _estimate_payload_bytes(payload)
    usage = get_or_create_current_period_usage(api_key.tenant_id, db=db)
    assert_limit(
        entitlements,
        "events_per_month",
        int(usage.events_ingested or 0),
        mode="hard",
        message="Ingest quota exceeded for plan",
    )

    with trace_span(
        "ingest.browser",
        tenant_id=api_key.tenant_id,
        website_id=website.id,
        environment_id=environment.id,
        event_type=payload.type,
    ):
        if payload.session_id:
            with trace_span(
                "ingest.session_upsert",
                tenant_id=api_key.tenant_id,
                session_id=payload.session_id,
            ):
                upsert_behaviour_session(
                    db,
                    tenant_id=api_key.tenant_id,
                    website_id=website.id,
                    environment_id=environment.id,
                    session_id=payload.session_id,
                    event_type=payload.type,
                    event_ts=payload.ts,
                    path=event_path,
                    ip_hash=ip_hash,
                )

        try:
            with trace_span(
                "ingest.event_insert",
                tenant_id=api_key.tenant_id,
                event_id=payload.event_id,
            ):
                create_behaviour_event(
                    db,
                    tenant_id=api_key.tenant_id,
                    website_id=website.id,
                    environment_id=environment.id,
                    event_id=payload.event_id,
                    event_type=payload.type,
                    url=payload.url,
                    event_ts=payload.ts,
                    ingested_at=datetime.utcnow(),
                    path=event_path,
                    referrer=payload.referrer,
                    session_id=payload.session_id,
                    visitor_id=payload.user_id,
                    meta=payload.meta,
                    ip_hash=ip_hash,
                    client_ip=client_ip,
                    user_agent=user_agent,
                )
        except IntegrityError:
            db.rollback()
            existing_event = get_behaviour_event_by_event_id(
                db,
                tenant_id=api_key.tenant_id,
                environment_id=environment.id,
                event_id=payload.event_id,
            )
            if existing_event:
                mark_api_key_used(db, api_key.public_key)
                record_ingest_event(
                    tenant_id=api_key.tenant_id,
                    website_id=website.id,
                    environment_id=environment.id,
                    event_type=payload.type,
                    ingest_type=ingest_type,
                )
                record_ingest_latency(
                    ingest_type=ingest_type,
                    duration_ms=(monotonic() - start_time) * 1000.0,
                )
                return IngestBrowserResponse(
                    ok=True,
                    received_at=datetime.utcnow(),
                    request_id=request_id,
                    deduped=True,
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to ingest event",
            )

        try:
            queue_first_event_email(db, tenant_id=api_key.tenant_id)
        except Exception:
            logger.exception("Failed to queue first event email")

        if payload.stack_hints:
            try:
                apply_stack_detection(
                    db,
                    tenant_id=api_key.tenant_id,
                    website_id=website.id,
                    hints=payload.stack_hints,
                )
            except Exception:
                db.rollback()
                logger.exception("Stack detection failed")

        try:
            anomaly_ctx = AnomalyContext(
                tenant_id=api_key.tenant_id,
                website_id=website.id,
                environment_id=environment.id,
                session_id=payload.session_id,
                event_id=payload.event_id,
            )
            with trace_span(
                "ingest.anomaly_eval",
                tenant_id=api_key.tenant_id,
                event_id=payload.event_id,
            ):
                signals = evaluate_event_for_anomaly(anomaly_ctx, payload)
            if signals:
                for signal in signals:
                    db.add(
                        AnomalySignalEvent(
                            tenant_id=api_key.tenant_id,
                            website_id=website.id,
                            environment_id=environment.id,
                            signal_type=signal.type,
                            severity=signal.severity,
                            session_id=payload.session_id,
                            event_id=payload.event_id,
                            summary={
                                "event_type": payload.type,
                                "path": event_path,
                                "evidence": signal.evidence,
                            },
                        )
                    )
                db.commit()
        except Exception:
            db.rollback()
            logger.exception("Anomaly evaluation failed")

    mark_api_key_used(db, api_key.public_key)
    increment_events(api_key.tenant_id, 1, db=db)
    increment_storage(api_key.tenant_id, payload_bytes, db=db)
    record_ingest_event(
        tenant_id=api_key.tenant_id,
        website_id=website.id,
        environment_id=environment.id,
        event_type=payload.type,
        ingest_type=ingest_type,
    )
    record_ingest_latency(
        ingest_type=ingest_type,
        duration_ms=(monotonic() - start_time) * 1000.0,
    )
    return IngestBrowserResponse(
        ok=True,
        received_at=datetime.utcnow(),
        request_id=request_id,
        deduped=False,
    )
