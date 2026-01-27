# This module captures audit events and pushes them to tenant-scoped listeners.

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Set
import csv
import io
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from jose import JWTError
from sqlalchemy.orm import Session
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.db import SessionLocal, get_db
from app.core.security import decode_access_token, is_token_revoked
from app.entitlements.resolver import resolve_entitlements_for_tenant
from app.crud.audit import create_audit_log, get_audit_logs
from app.crud.tenants import get_tenant_by_id, get_tenant_by_slug
from app.crud.users import get_user_by_username
from app.models.memberships import Membership
from app.models.audit_logs import AuditLog
from app.models.enums import RoleEnum
from app.schemas.audit import AuditLogCreate, AuditLogRead
from app.tenancy.constants import TENANT_HEADER
from app.tenancy.dependencies import require_roles, require_tenant_context

# Router setup — all routes here live under /api/audit.
router = APIRouter(prefix="/audit", tags=["audit"])

# In-memory tenant-specific websocket listeners.
_listeners: Dict[int, Set[WebSocket]] = {}


def _resolve_tenant_id(db: Session, tenant_hint: str | None) -> int | None:
    if not tenant_hint:
        return None
    tenant_value = tenant_hint.strip()
    tenant = (
        get_tenant_by_id(db, int(tenant_value))
        if tenant_value.isdigit()
        else get_tenant_by_slug(db, tenant_value)
    )
    if not tenant:
        return None
    return tenant.id


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _coerce_positive_int(value) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _build_audit_query(
    db: Session,
    tenant_id: int,
    *,
    from_ts: datetime | None,
    to_ts: datetime | None,
    actor: str | None,
    action: str | None,
    resource: str | None,
):
    query = db.query(AuditLog).filter(AuditLog.tenant_id == tenant_id)
    if from_ts is not None:
        query = query.filter(AuditLog.timestamp >= from_ts)
    if to_ts is not None:
        query = query.filter(AuditLog.timestamp <= to_ts)
    if actor:
        query = query.filter(AuditLog.username == actor)
    if action:
        query = query.filter(AuditLog.event == action)
    if resource:
        query = query.filter(AuditLog.request_path == resource)
    return query.order_by(AuditLog.timestamp.desc())


def _serialize_audit_row(
    row: AuditLog,
    *,
    allow_raw_ip: bool,
    raw_ip_cutoff: datetime | None,
    allow_ip_hash: bool,
) -> dict[str, object | None]:
    include_raw_ip = (
        allow_raw_ip
        and row.client_ip
        and raw_ip_cutoff is not None
        and row.timestamp >= raw_ip_cutoff
    )
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "username": row.username,
        "event": row.event,
        "timestamp": row.timestamp.isoformat() if row.timestamp else None,
        "request_path": row.request_path,
        "referrer": row.referrer,
        "user_agent": row.user_agent,
        "client_ip": row.client_ip if include_raw_ip else None,
        "ip_hash": row.ip_hash if allow_ip_hash else None,
        "country_code": row.country_code,
        "region": row.region,
        "city": row.city,
        "latitude": row.latitude,
        "longitude": row.longitude,
        "asn": row.asn,
        "is_datacenter": row.is_datacenter,
    }


def _parse_bearer_token(ws: WebSocket) -> str | None:
    auth_header = ws.headers.get("authorization")
    if not auth_header:
        return None
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1]


def _authorize_websocket(db: Session, ws: WebSocket) -> int | None:
    token = _parse_bearer_token(ws)
    if not token:
        return None
    if is_token_revoked(token):
        return None
    try:
        payload = decode_access_token(token)
    except JWTError:
        return None
    username = payload.get("sub")
    if not username:
        return None
    user = get_user_by_username(db, username)
    if not user:
        return None
    header_name = settings.TENANT_HEADER_NAME or TENANT_HEADER
    tenant_id = _resolve_tenant_id(db, ws.headers.get(header_name))
    if not tenant_id:
        return None
    membership = (
        db.query(Membership)
        .filter(
            Membership.tenant_id == tenant_id,
            Membership.user_id == user.id,
            Membership.status == "active",
        )
        .first()
    )
    if not membership:
        return None
    return tenant_id


@router.websocket("/ws")
async def audit_ws(ws: WebSocket):
    """Register a websocket to receive audit events."""
    with SessionLocal() as db:
        tenant_id = _authorize_websocket(db, ws)
    if tenant_id is None:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await ws.accept()
    _listeners.setdefault(tenant_id, set()).add(ws)
    try:
        while True:
            # FastAPI requires a receive call to keep the connection alive.
            await ws.receive_text()
    except WebSocketDisconnect:
        listeners = _listeners.get(tenant_id)
        if listeners and ws in listeners:
            listeners.remove(ws)
            if not listeners:
                _listeners.pop(tenant_id, None)


async def _broadcast(tenant_id: int, event: str) -> None:
    """Send an audit event to all listeners in a tenant."""
    listeners = list(_listeners.get(tenant_id, set()))
    for ws in listeners:
        try:
            await ws.send_json({"event": event})
        except Exception:
            tenant_listeners = _listeners.get(tenant_id)
            if tenant_listeners and ws in tenant_listeners:
                tenant_listeners.remove(ws)
                if not tenant_listeners:
                    _listeners.pop(tenant_id, None)


@router.get("/", response_model=List[AuditLogRead])
def read_audit_logs(
    db: Session = Depends(get_db),
    ctx=Depends(require_tenant_context(user_resolver=get_current_user)),
    limit: int = 100,
    offset: int = 0,
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    if tenant_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return get_audit_logs(db, tenant_id, limit=limit, offset=offset)


@router.post("/log")
async def audit_log(
    log: AuditLogCreate,
    request: Request,
    db: Session = Depends(get_db),
    ctx=Depends(require_tenant_context(user_resolver=get_current_user)),
):
    """Record an audit event from a frontend and broadcast to listeners."""
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    if tenant_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    username = log.username or ctx.username
    create_audit_log(db, tenant_id, username, log.event.value, request=request)
    await _broadcast(tenant_id, log.event.value)
    return {"status": "logged"}


@router.get("/export")
def export_audit_logs(
    db: Session = Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
    format: str = "json",
    from_ts: str | None = Query(None, alias="from"),
    to_ts: str | None = Query(None, alias="to"),
    actor: str | None = None,
    action: str | None = None,
    resource: str | None = None,
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    if tenant_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    fmt = (format or "json").lower()
    if fmt not in {"csv", "json"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported export format")

    parsed_from = _parse_datetime(from_ts)
    parsed_to = _parse_datetime(to_ts)
    if parsed_from and parsed_to and parsed_from > parsed_to:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date range")

    actor = actor.strip() if actor else None
    action = action.strip() if action else None
    resource = resource.strip() if resource else None

    entitlements = resolve_entitlements_for_tenant(db, tenant_id)
    limits = entitlements.get("limits", {}) if entitlements else {}
    features = entitlements.get("features", {}) if entitlements else {}
    max_days = _coerce_positive_int(limits.get("event_retention_days") or limits.get("retention_days"))
    if max_days and parsed_from and parsed_to:
        if parsed_to - parsed_from > timedelta(days=max_days):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Date range exceeds plan limits")

    raw_ip_days = _coerce_positive_int(limits.get("raw_ip_retention_days"))
    raw_ip_cutoff = (
        datetime.utcnow() - timedelta(days=raw_ip_days)
        if raw_ip_days
        else None
    )
    allow_raw_ip = bool(settings.ALLOW_RAW_IP_SECURITY_ENDPOINTS and raw_ip_cutoff)
    allow_ip_hash = bool(features.get("audit_export_ip_hash"))

    export_filters = {
        "from": parsed_from.isoformat() if parsed_from else None,
        "to": parsed_to.isoformat() if parsed_to else None,
        "actor": actor,
        "action": action,
        "resource": resource,
    }
    meta = {
        "tenant_id": tenant_id,
        "generated_at": datetime.utcnow().isoformat(),
        "requested_by": ctx.username,
        "format": fmt,
        "filters": export_filters,
        "ip_hash_included": allow_ip_hash,
        "raw_ip_included": allow_raw_ip,
    }

    query = _build_audit_query(
        db,
        tenant_id,
        from_ts=parsed_from,
        to_ts=parsed_to,
        actor=actor,
        action=action,
        resource=resource,
    )

    create_audit_log(
        db,
        tenant_id=tenant_id,
        username=ctx.username,
        event="audit.export",
        request=None,
    )

    timestamp_label = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    filename = f"audit_export_{tenant_id}_{timestamp_label}.{fmt}"

    if fmt == "json":
        def json_stream():
            yield "{\"meta\":" + json.dumps(meta, separators=(",", ":")) + ",\"records\":["
            first = True
            for row in query.yield_per(500):
                payload = _serialize_audit_row(
                    row,
                    allow_raw_ip=allow_raw_ip,
                    raw_ip_cutoff=raw_ip_cutoff,
                    allow_ip_hash=allow_ip_hash,
                )
                chunk = json.dumps(payload)
                if not first:
                    chunk = "," + chunk
                first = False
                yield chunk
            yield "]}"

        response = StreamingResponse(json_stream(), media_type="application/json")
    else:
        headers = [
            "id",
            "tenant_id",
            "username",
            "event",
            "timestamp",
            "request_path",
            "referrer",
            "user_agent",
            "client_ip",
            "ip_hash",
            "country_code",
            "region",
            "city",
            "latitude",
            "longitude",
            "asn",
            "is_datacenter",
        ]

        def csv_stream():
            yield f"# tenant_id={tenant_id}\n"
            yield f"# generated_at={meta['generated_at']}\n"
            yield f"# requested_by={meta['requested_by']}\n"
            yield f"# filters={json.dumps(export_filters, separators=(',', ':'))}\n"
            yield f"# ip_hash_included={allow_ip_hash}\n"
            yield f"# raw_ip_included={allow_raw_ip}\n"
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(headers)
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)
            for row in query.yield_per(500):
                payload = _serialize_audit_row(
                    row,
                    allow_raw_ip=allow_raw_ip,
                    raw_ip_cutoff=raw_ip_cutoff,
                    allow_ip_hash=allow_ip_hash,
                )
                writer.writerow([payload.get(col) for col in headers])
                yield buffer.getvalue()
                buffer.seek(0)
                buffer.truncate(0)

        response = StreamingResponse(csv_stream(), media_type="text/csv")

    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    response.headers["X-Export-Streaming"] = "1"
    return response
