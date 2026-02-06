from __future__ import annotations

from datetime import datetime
import gzip
import json
import logging
from ipaddress import ip_address
from time import monotonic
from typing import Any
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
from app.core.sampling import (
    is_high_priority_event,
    resolve_sampling_config,
    should_keep_event,
)
from app.core.usage import (
    get_or_create_current_period_usage,
    increment_aggregate_rows,
    increment_events,
    increment_raw_events,
    increment_sampled_out,
    increment_storage,
)
from app.core.privacy import hash_ip
from app.core.rate_limit import allow, is_banned, register_abuse_attempt, register_invalid_attempt
from app.core.tracing import trace_span
from app.core.utils.domain import normalize_domain
from app.crud.api_keys import get_api_key_by_public_key, mark_api_key_used
from app.crud.behaviour_events import create_behaviour_events_bulk
from app.crud.behaviour_sessions import upsert_behaviour_sessions_bulk
from app.crud.tenant_settings import get_settings
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


def _decode_request_body(request: Request) -> bytes:
    encoding = (request.headers.get("Content-Encoding") or "").lower()
    raw = request._body  # type: ignore[attr-defined]
    if raw is None:
        raw = b""
    if "gzip" in encoding:
        try:
            raw = gzip.decompress(raw)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to decompress payload",
            ) from exc
    return raw


async def _read_payload_json(request: Request) -> Any:
    _enforce_body_limit(request)
    raw = await request.body()
    if raw and len(raw) > settings.INGEST_MAX_BODY_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Payload too large",
        )
    request._body = raw  # type: ignore[attr-defined]
    decoded = _decode_request_body(request)
    if decoded and len(decoded) > settings.INGEST_MAX_BODY_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Payload too large",
        )
    try:
        return json.loads(decoded.decode("utf-8") if decoded else "{}")
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        ) from exc


def _parse_event_payload(payload: Any) -> IngestBrowserEvent:
    try:
        return IngestBrowserEvent.model_validate(payload)
    except AttributeError:
        return IngestBrowserEvent.parse_obj(payload)


def _parse_events_payload(payload: Any) -> list[IngestBrowserEvent]:
    if isinstance(payload, dict) and "events" in payload:
        candidate = payload.get("events")
    else:
        candidate = payload

    events: list[Any]
    if isinstance(candidate, list):
        events = candidate
    elif candidate:
        events = [candidate]
    else:
        events = []
    if not events:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No events provided")
    if len(events) > settings.INGEST_MAX_BATCH_EVENTS:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Batch size too large",
        )
    parsed: list[IngestBrowserEvent] = []
    for entry in events:
        parsed.append(_parse_event_payload(entry))
    return parsed


@router.post("/browser", response_model=IngestBrowserResponse)
async def ingest_browser_event(
    request: Request,
    db: Session = Depends(get_db),
):
    start_time = monotonic()
    ingest_type = "browser"
    payload_json = await _read_payload_json(request)
    events = _parse_events_payload(payload_json)

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

    entitlements = resolve_effective_entitlements(db, api_key.tenant_id)
    limits = entitlements.get("limits", {})
    rpm_limit = _coerce_positive_int(limits.get("ingest_rpm"), settings.INGEST_DEFAULT_RPM)
    burst_limit = _coerce_positive_int(limits.get("ingest_burst"), settings.INGEST_DEFAULT_BURST)

    for _ in range(len(events)):
        key_allowed, key_retry = allow(
            f"ingest:key:{api_key.public_key}",
            capacity=burst_limit,
            refill_rate_per_sec=rpm_limit / 60.0,
        )
        if not key_allowed:
            _raise_rate_limit(key_retry, "Rate limit exceeded")

    if ip_hash:
        for _ in range(len(events)):
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

    settings_row = None
    try:
        settings_row = get_settings(db, api_key.tenant_id)
    except Exception:
        settings_row = None
    sampling_default_rate, sampling_rules = resolve_sampling_config(
        settings_row,
        default_rate=settings.INGEST_SAMPLING_DEFAULT_RATE,
    )

    usage = get_or_create_current_period_usage(api_key.tenant_id, db=db)
    current_usage = int(usage.events_ingested or 0)
    limit_value = _coerce_positive_int(limits.get("events_per_month"), 0)
    remaining_quota = limit_value - current_usage if limit_value else None

    accepted_events: list[IngestBrowserEvent] = []
    event_paths: dict[str, str] = {}
    dropped_domain = 0
    dropped_sampled = 0
    for event in events:
        if not _matches_domain(event.url, website.domain):
            dropped_domain += 1
            continue
        path_value = event.path or normalize_path(urlsplit(event.url).path or "/")
        event_paths[event.event_id] = path_value
        if not should_keep_event(
            event_type=event.type,
            path=path_value,
            rules=sampling_rules,
            default_rate=sampling_default_rate,
        ):
            dropped_sampled += 1
            continue
        accepted_events.append(event)

    if dropped_sampled:
        increment_sampled_out(api_key.tenant_id, dropped_sampled, db=db)

    if not accepted_events:
        detail = "Domain mismatch" if dropped_domain else "All events sampled"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    def _is_high_priority(event: IngestBrowserEvent) -> bool:
        path_value = event_paths.get(event.event_id)
        return is_high_priority_event(event.type, path_value)

    if remaining_quota is not None and remaining_quota <= 0:
        high_priority = [event for event in accepted_events if _is_high_priority(event)]
        if not high_priority:
            _raise_rate_limit(60, "Ingest quota exceeded for plan")
        accepted_events = high_priority

    if remaining_quota is not None and remaining_quota > 0 and len(accepted_events) > remaining_quota:
        high_priority = [event for event in accepted_events if _is_high_priority(event)]
        low_priority = [event for event in accepted_events if not _is_high_priority(event)]
        accepted_events = high_priority + low_priority
        accepted_events = accepted_events[:remaining_quota]

    event_ids = [event.event_id for event in accepted_events]
    existing_event_ids: set[str] = set()
    if event_ids:
        from app.models.behaviour_events import BehaviourEvent

        existing_event_ids = {
            row[0]
            for row in (
                db.query(BehaviourEvent.event_id)
                .filter(
                    BehaviourEvent.tenant_id == api_key.tenant_id,
                    BehaviourEvent.environment_id == environment.id,
                    BehaviourEvent.event_id.in_(event_ids),
                )
                .all()
            )
        }

    deduped_count = 0
    unique_events: list[IngestBrowserEvent] = []
    seen_ids: set[str] = set()
    for event in accepted_events:
        if event.event_id in seen_ids:
            deduped_count += 1
            continue
        seen_ids.add(event.event_id)
        if event.event_id in existing_event_ids:
            deduped_count += 1
            continue
        unique_events.append(event)

    if not unique_events:
        mark_api_key_used(db, api_key.public_key)
        record_ingest_latency(
            ingest_type=ingest_type,
            duration_ms=(monotonic() - start_time) * 1000.0,
        )
        total_dropped = dropped_domain + dropped_sampled + deduped_count
        return IngestBrowserResponse(
            ok=True,
            received_at=datetime.utcnow(),
            request_id=request_id,
            deduped=True,
            accepted=0,
            dropped=total_dropped,
            deduped_count=deduped_count,
            sampled_out=dropped_sampled,
        )

    event_rows: list[dict[str, Any]] = []
    session_updates: list[dict[str, Any]] = []
    payload_bytes = 0
    stack_hints = None
    for event in unique_events:
        event_path = event_paths.get(event.event_id) or normalize_path(urlsplit(event.url).path or "/")
        event_rows.append(
            {
                "tenant_id": api_key.tenant_id,
                "website_id": website.id,
                "environment_id": environment.id,
                "event_id": event.event_id,
                "event_type": event.type,
                "url": event.url,
                "event_ts": event.ts,
                "ingested_at": datetime.utcnow(),
                "path": event_path,
                "referrer": event.referrer,
                "session_id": event.session_id,
                "visitor_id": event.user_id,
                "meta": event.meta,
                "ip_hash": ip_hash,
                "user_agent": user_agent,
            }
        )
        payload_bytes += _estimate_payload_bytes(event)
        if event.session_id:
            session_updates.append(
                {
                    "session_id": event.session_id,
                    "event_type": event.type,
                    "event_ts": event.ts,
                    "path": event_path,
                    "ip_hash": ip_hash,
                }
            )
        if stack_hints is None and event.stack_hints:
            stack_hints = event.stack_hints

    inserted_count = 0
    sessions_touched = 0
    with trace_span(
        "ingest.browser",
        tenant_id=api_key.tenant_id,
        website_id=website.id,
        environment_id=environment.id,
    ):
        try:
            if session_updates:
                with trace_span(
                    "ingest.session_upsert",
                    tenant_id=api_key.tenant_id,
                ):
                    sessions_touched = upsert_behaviour_sessions_bulk(
                        db,
                        tenant_id=api_key.tenant_id,
                        website_id=website.id,
                        environment_id=environment.id,
                        updates=session_updates,
                        commit=False,
                    )
            with trace_span(
                "ingest.event_insert",
                tenant_id=api_key.tenant_id,
            ):
                inserted_count = create_behaviour_events_bulk(
                    db,
                    events=event_rows,
                    commit=False,
                )
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to ingest event batch",
            )

    try:
        queue_first_event_email(db, tenant_id=api_key.tenant_id)
    except Exception:
        logger.exception("Failed to queue first event email")

    if stack_hints:
        try:
            apply_stack_detection(
                db,
                tenant_id=api_key.tenant_id,
                website_id=website.id,
                hints=stack_hints,
            )
        except Exception:
            db.rollback()
            logger.exception("Stack detection failed")

    try:
        for event in unique_events:
            anomaly_ctx = AnomalyContext(
                tenant_id=api_key.tenant_id,
                website_id=website.id,
                environment_id=environment.id,
                session_id=event.session_id,
                event_id=event.event_id,
            )
            with trace_span(
                "ingest.anomaly_eval",
                tenant_id=api_key.tenant_id,
                event_id=event.event_id,
            ):
                signals = evaluate_event_for_anomaly(anomaly_ctx, event)
            if signals:
                event_path = event_paths.get(event.event_id) or normalize_path(
                    urlsplit(event.url).path or "/"
                )
                for signal in signals:
                    db.add(
                        AnomalySignalEvent(
                            tenant_id=api_key.tenant_id,
                            website_id=website.id,
                            environment_id=environment.id,
                            signal_type=signal.type,
                            severity=signal.severity,
                            session_id=event.session_id,
                            event_id=event.event_id,
                            summary={
                                "event_type": event.type,
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
    if inserted_count:
        increment_events(api_key.tenant_id, inserted_count, db=db)
        increment_raw_events(api_key.tenant_id, inserted_count, db=db)
        increment_storage(api_key.tenant_id, payload_bytes, db=db)
    if sessions_touched:
        increment_aggregate_rows(api_key.tenant_id, sessions_touched, db=db)
    for event in unique_events:
        record_ingest_event(
            tenant_id=api_key.tenant_id,
            website_id=website.id,
            environment_id=environment.id,
            event_type=event.type,
            ingest_type=ingest_type,
        )
    record_ingest_latency(
        ingest_type=ingest_type,
        duration_ms=(monotonic() - start_time) * 1000.0,
    )
    total_dropped = dropped_domain + dropped_sampled + deduped_count + (len(unique_events) - inserted_count)
    return IngestBrowserResponse(
        ok=True,
        received_at=datetime.utcnow(),
        request_id=request_id,
        deduped=False,
        accepted=inserted_count,
        dropped=total_dropped,
        deduped_count=deduped_count,
        sampled_out=dropped_sampled,
    )
