
# This module is all about **capturing audit events** (like logins,
# logouts, sensitive actions) and pushing them to interested clients.
# The key idea is: every time the frontend calls POST /api/audit/log,
# we persist that event to the DB *and* broadcast it live to all active
# WebSocket listeners. That way dashboards can update in real time.

from typing import List
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.crud.audit import create_audit_log
from app.schemas.audit import AuditLogCreate

# Router setup — all routes here live under /api/audit.
# Grouped under the "audit" tag so Swagger / OpenAPI docs look tidy.
router = APIRouter(prefix="/api/audit", tags=["audit"])

# In-memory list of connected WebSocket clients.
# This is super lightweight: just a plain list we append/remove from.
# For bigger systems, you’d use Redis pub/sub or another broker,
# but here we keep it simple and local.
_listeners: List[WebSocket] = []


# Any client can connect here to "subscribe" to audit events.
# We accept the socket, keep it in our _listeners list, and then
# sit in a receive loop (even though we don’t *need* the messages).
# If the client disconnects, we clean it up to avoid memory leaks.
@router.websocket("/ws")
async def audit_ws(ws: WebSocket):
    """Register a websocket to receive audit events."""
    await ws.accept()
    _listeners.append(ws)
    try:
        while True:
            # We don’t actually care what the client sends, but FastAPI
            # requires a receive call to keep the connection alive.
            await ws.receive_text()
    except WebSocketDisconnect:
        # Remove the socket so we don’t try to send to a dead connection.
        if ws in _listeners:
            _listeners.remove(ws)


# This pushes an event string to every connected WebSocket client.
# We iterate over a copy of the list so we can safely remove dead
# sockets mid-loop. If sending fails, we assume the connection is
# broken and drop it from the list.
async def _broadcast(event: str) -> None:
    """Send an audit event to all listeners."""
    for ws in list(_listeners):
        try:
            await ws.send_json({"event": event})
        except Exception:
            _listeners.remove(ws)

# This is the main entrypoint for the frontend. It posts an event
# (like "user_login_success") along with the username. We store it
# in the DB for history/audit trails, then immediately broadcast
# it to any live WebSocket clients. The response is kept minimal
# because the real-time broadcast is the star of the show.
@router.post("/log")
async def audit_log(log: AuditLogCreate, db: Session = Depends(get_db)):
    """Record an audit event from a frontend and broadcast to listeners."""
    # First: persist event into DB (so nothing is lost even if no clients).
    create_audit_log(db, log.username, log.event.value)

    # Then: fire off a live broadcast so dashboards update instantly.
    await _broadcast(log.event.value)

    # Finally: confirm back to the caller that we logged it.
    return {"status": "logged"}
