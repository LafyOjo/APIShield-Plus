# This module captures audit events and pushes them to tenant-scoped listeners.

from typing import Dict, List, Set

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from jose import JWTError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.db import SessionLocal, get_db
from app.core.security import decode_access_token, is_token_revoked
from app.crud.audit import create_audit_log, get_audit_logs
from app.crud.tenants import get_tenant_by_id, get_tenant_by_slug
from app.crud.users import get_user_by_username
from app.models.memberships import Membership
from app.schemas.audit import AuditLogCreate, AuditLogRead
from app.tenancy.constants import TENANT_HEADER
from app.tenancy.dependencies import require_tenant_context

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
