
# This module defines the /score endpoint and related helpers.
# Its job is to track login attempts, raise alerts when 
# failures stack up, and block abusive clients (e.g. bots 
# doing credential stuffing). 
#
# It integrates with Prometheus (for metrics), the database 
# (to store alerts), and the in-memory FAILED_USER_ATTEMPTS 
# dict (for quick per-user rate limiting).

from typing import Any, Dict
from datetime import datetime, timedelta, timezone
import os
from fastapi import APIRouter, Depends, HTTPException, Request
from prometheus_client import Counter
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.alerts import Alert
import app.api.security as security
from app.core.events import log_event

router = APIRouter(
    prefix="",            
    tags=["score"],
    responses={404: {"description": "Not Found"}},
)


# FAIL_LIMIT: how many failed logins are allowed before blocking
# FAIL_WINDOW_SECONDS: the time window in which to count failures
# Both can be overridden with environment variables so tests 
# and deployments can easily adjust security sensitivity.
DEFAULT_FAIL_LIMIT = int(os.getenv("FAIL_LIMIT", "5"))
DEFAULT_FAIL_WINDOW_SECONDS = int(os.getenv("FAIL_WINDOW_SECONDS", "60"))


# These let us track how many attempts are happening, broken
# down by IP and whether a JWT was included or not.
LOGIN_ATTEMPTS = Counter(
    "login_attempts_ip_total",
    "Total login attempts by IP",
    ["ip"],
)

JWT_LOGIN_ATTEMPTS = Counter(
    "login_attempts_jwt_total",
    "Login attempts that included a JWT",
    ["ip"],
)

NO_JWT_LOGIN_ATTEMPTS = Counter(
    "login_attempts_no_jwt_total",
    "Login attempts without a JWT",
    ["ip"],
)

STUFFING_DETECTIONS = Counter(
    "credential_stuffing_total",
    "Detected credential stuffing attempts",
    ["ip"],
)

# In-memory tracker for per-user failed attempts
FAILED_USER_ATTEMPTS: Dict[int, list[datetime]] = {}



# Helper to check if a user_id has exceeded their failure
# threshold within the configured window. This is per-user,
# not per-IP. Returns True if the account should be locked.
def is_rate_limited(db: Session, user_id: int, limit: int) -> bool:
    window_seconds = int(os.getenv("FAIL_WINDOW_SECONDS", DEFAULT_FAIL_WINDOW_SECONDS))
    now = datetime.now(timezone.utc)
    attempts = FAILED_USER_ATTEMPTS.get(user_id, [])
    attempts = [t for t in attempts if now - t < timedelta(seconds=window_seconds)]
    FAILED_USER_ATTEMPTS[user_id] = attempts
    return len(attempts) >= limit


# Main function that records a login attempt (success/failure).
# - Always increments Prometheus metrics.
# - Clears per-user failures on success.
# - Logs events for monitoring.
# - Blocks IPs if too many failures happened in the time window.
def record_attempt(
    db: Session,
    client_ip: str,
    success: bool,
    *,
    with_jwt: bool = False,
    detail: str | None = None,
    user_id: int | None = None,
    fail_limit: int | None = None,
    username: str | None = None,
) -> Dict[str, Any]:
    """Record a login attempt and return a JSON status."""

    # Track attempt in Prometheus
    LOGIN_ATTEMPTS.labels(ip=client_ip).inc()
    if with_jwt:
        JWT_LOGIN_ATTEMPTS.labels(ip=client_ip).inc()
    else:
        NO_JWT_LOGIN_ATTEMPTS.labels(ip=client_ip).inc()

    # If success, reset counters and mark event
    if success:
        if user_id is not None:
            FAILED_USER_ATTEMPTS.pop(user_id, None)
        log_event(db, username, "stuffing_attempt", True)
        return {"status": "ok", "fails_last_minute": 0}

    # If failure, count how many recent fails for this IP
    ip_fail_limit = int(os.getenv("FAIL_LIMIT", DEFAULT_FAIL_LIMIT))
    window_seconds = int(os.getenv("FAIL_WINDOW_SECONDS", DEFAULT_FAIL_WINDOW_SECONDS))
    window_start = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
    fail_count = (
        db.query(Alert)
        .filter(Alert.ip_address == client_ip)
        .filter(Alert.timestamp >= window_start)
        .count()
    )

    # Track failures per-user as well
    if user_id is not None:
        window_seconds_user = int(os.getenv("FAIL_WINDOW_SECONDS", DEFAULT_FAIL_WINDOW_SECONDS))
        now = datetime.now(timezone.utc)
        attempts = FAILED_USER_ATTEMPTS.get(user_id, [])
        attempts = [t for t in attempts if now - t < timedelta(seconds=window_seconds_user)]
        attempts.append(now)
        if fail_limit is not None and len(attempts) > fail_limit:
            attempts = attempts[-fail_limit:]
        FAILED_USER_ATTEMPTS[user_id] = attempts

    # Log failed attempt in event log
    log_event(db, username, "stuffing_attempt", False)

    # If security is enabled and too many fails → BLOCK
    if security.SECURITY_ENABLED and fail_count >= ip_fail_limit:
        STUFFING_DETECTIONS.labels(ip=client_ip).inc()
        log_event(db, None, "stuffing_block", True)
        alert = Alert(
            ip_address=client_ip,
            total_fails=fail_count + 1,
            detail="Blocked: too many failures",
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        return {"status": "blocked", "fails_last_minute": fail_count + 1}

    # Otherwise just log the failed attempt as an alert
    alert = Alert(
        ip_address=client_ip,
        total_fails=fail_count + 1,
        detail=detail or "Failed login",
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return {"status": "ok", "fails_last_minute": fail_count + 1}



# Accepts POST payload:
# {
#   "client_ip": "10.0.0.1",
#   "auth_result": "success" | "failure",
#   "with_jwt": true/false,
#   "username": "alice"
# }
#
# Returns a dict like:
# { "status": "ok"|"blocked", "fails_last_minute": <int> }
@router.post("/score", response_model=Dict[str, Any])
def score(payload: Dict[str, Any], request: Request, db: Session = Depends(get_db)):
    """
    Core scoring endpoint that receives login results from 
    the frontend. It validates input, records attempts, and
    enforces credential stuffing protection rules.
    """
    if security.SECURITY_ENABLED:
        try:
            # Chain verification adds another Zero Trust layer
            security.verify_chain(request.headers.get("X-Chain-Password"))
        except HTTPException as exc:
            STUFFING_DETECTIONS.labels(ip=request.client.host).inc()
            log_event(db, None, "stuffing_block", True)
            alert = Alert(
                ip_address=request.client.host,
                total_fails=0,
                detail="Blocked: invalid chain token",
            )
            db.add(alert)
            db.commit()
            db.refresh(alert)
            raise exc

    client_ip = payload.get("client_ip")
    auth_result = payload.get("auth_result")
    with_jwt = bool(payload.get("with_jwt"))
    username = payload.get("username")

    if client_ip is None or auth_result not in ("success", "failure"):
        raise HTTPException(status_code=422, detail="Invalid payload")

    return record_attempt(
        db,
        client_ip,
        auth_result == "success",
        with_jwt=with_jwt,
        username=username,
    )
