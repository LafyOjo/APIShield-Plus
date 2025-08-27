# This file is all about logging and retrieving authentication events.
# Whenever someone tries to log in (successfully or not), we capture
# the attempt, enrich it with client details, and push it into both
# the DB (for history) and Prometheus metrics (for monitoring).
# That way, we can track login success/fail trends, detect credential
# stuffing, and measure request latency in real time.
# 

from typing import List
import time

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.auth_events import AuthEventCreate, AuthEventOut
from app.crud.auth_events import create_auth_event, get_auth_events
from app.core.metrics import (
    record_login_attempt,
    record_credential_stuffing,
    record_block,
    login_request_duration_seconds,
)

# Router groups all auth-event routes under /events/auth
# Keeping it separate from audit logs because this is focused
# specifically on authentication attempts (not generic actions).
router = APIRouter(prefix="/events", tags=["auth-events"])


# This endpoint is called on every login attempt. We:
#   1. Extract username, client IP, success/fail flags, etc.
#   2. Record Prometheus metrics for monitoring and alerting.
#   3. Insert the event into the database for long-term audit.
# Finally, we wrap it in a timer so we can measure request latency.
@router.post("/auth", response_model=AuthEventOut)
def log_auth_event(
    payload: AuthEventCreate, request: Request, db: Session = Depends(get_db)
) -> AuthEventOut:
    t0 = time.perf_counter()  # mark start time to measure duration
    try:
        # Extract the username from payload or fallback
        username = (payload.username or "unknown")

        # Get client IP — useful for detecting suspicious login sources
        client_ip = request.client.host if request.client else "unknown"

        # Booleans make sure we never deal with None in DB/metrics
        success = bool(payload.success)
        is_stuff = bool(payload.is_credential_stuffing)
        blocked = bool(payload.blocked)
        block_rule = payload.block_rule or ""

        # Record Prometheus counters to track login behavior
        record_login_attempt(username, success)
        if is_stuff:
            record_credential_stuffing(username)
        if blocked:
            record_block(block_rule, username, client_ip)

        # Store this event in DB for auditing and later queries
        return create_auth_event(db, username, payload.action, success, payload.source)

    finally:
        # No matter what happens, record the time this took
        # Observed duration helps detect slow auth paths.
        login_request_duration_seconds.observe(time.perf_counter() - t0)


# Provides a paginated feed of recent authentication events.
# Useful for dashboards, security monitoring, or forensic reviews.
# Defaults to 50 records but supports limit/offset for paging.
@router.get("/auth", response_model=List[AuthEventOut])
def read_auth_events(
    limit: int = 50, offset: int = 0, db: Session = Depends(get_db)
) -> List[AuthEventOut]:
    return get_auth_events(db, limit=limit, offset=offset)
