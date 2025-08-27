# Lightweight “risk policy” middleware. It checks recent failed
# login alerts from the same client IP and, if there are too many
# within a short window, blocks unauthenticated requests by default.
# Useful as a simple WAF-style guard in front of sensitive routes.

import os
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from fastapi import Request
from starlette.responses import JSONResponse
from starlette.status import HTTP_403_FORBIDDEN

from app.models.alerts import Alert

# Configure a module-level logger so we can report DB issues
# or policy decisions without spamming the global logging config.
log = logging.getLogger(__name__)

# Tunable knobs via env vars so ops can adjust behavior without redeploys.
# FAIL_LIMIT = how many failures within the window before we start blocking.
# POLICY_FAIL_MODE controls how we behave if our DB check fails (open vs closed).
FAIL_LIMIT = int(os.getenv("FAIL_LIMIT", 5))
FAIL_WINDOW_SECONDS = int(os.getenv("FAIL_WINDOW_SECONDS", 60))
POLICY_FAIL_MODE = os.getenv("POLICY_FAIL_MODE", "open").lower()  # "open" or "closed"

# A curated list of routes that should *never* be blocked by policy.
# These include health endpoints, docs, auth, scoring, and telemetry.
# You can extend the list via POLICY_SKIP_PATHS (comma-separated).
DEFAULT_SKIP_PATHS = (
    "/metrics", "/ping", "/health", "/healthz",
    "/docs", "/openapi.json",
    "/score",                 # scoring stays open
    "/login", "/register",    # allow auth
    "/api/token",
    "/api/audit/log",         # telemetry/logging
    "/events/auth",           # your auth-event hook
    "/favicon.ico",
)
EXTRA_SKIP = tuple(p.strip() for p in os.getenv("POLICY_SKIP_PATHS", "").split(",") if p.strip())
# Use dict.fromkeys to de-dup while preserving order.
SKIP_PATHS = tuple(dict.fromkeys([*DEFAULT_SKIP_PATHS, *EXTRA_SKIP]))


def assess_risk(db: Session, client_ip: str | None) -> bool:
    """
    Decide if a request should be allowed based on recent failed attempts.

    We look back a short window and count Alert rows for this IP. If the count
    hits or exceeds FAIL_LIMIT, we consider the request risky and return False.
    Any DB error falls back to POLICY_FAIL_MODE so we’re explicit about fail-open/closed.
    """
    if not client_ip:
        # No IP to judge: allow rather than block on missing context.
        return True
    since = datetime.utcnow() - timedelta(seconds=FAIL_WINDOW_SECONDS)
    try:
        count = (
            db.query(Alert)
              .filter(Alert.ip_address == client_ip, Alert.timestamp >= since)
              .count()
        )
        return count < FAIL_LIMIT
    except SQLAlchemyError as exc:
        # If the DB check fails, honor the configured fail mode.
        log.warning("Policy DB check failed; mode=%s; error=%s", POLICY_FAIL_MODE, exc)
        return POLICY_FAIL_MODE == "open"


class PolicyEngineMiddleware:
    """
    ASGI middleware that enforces a minimal IP-based risk policy.

    Flow:
      1) Skip non-HTTP and CORS preflight.
      2) Skip safe paths and already-authenticated requests.
      3) For everything else, check recent failures for the client IP.
      4) If risky, short-circuit with 403; otherwise, pass through.
    """

    def __init__(self, app):
        # Keep a reference to the downstream app so we can forward requests
        # after our quick pre-checks and policy decision.
        self.app = app

    async def __call__(self, scope, receive, send):
        # Only act on HTTP requests. WebSocket or other types are passed as-is.
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)

        # Always allow CORS preflight requests to avoid breaking browsers.
        if scope.get("method") == "OPTIONS":
            return await self.app(scope, receive, send)

        # Build a Request object so we can easily check headers and path.
        request = Request(scope, receive=receive)
        path = request.url.path

        # Infrastructure, docs, auth, and telemetry routes are never blocked.
        if path in SKIP_PATHS:
            return await self.app(scope, receive, send)

        # If the request already carries a Bearer token, let it through.
        # The assumption: authenticated callers have already jumped a hoop.
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            return await self.app(scope, receive, send)

        # Derive a client IP — prefer X-Forwarded-For (respecting proxies),
        # and fall back to the socket’s peer address if not present.
        client_ip = (
            request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or (request.client.host if request.client else None)
        )

        # Use a short-lived DB session to check risk for this IP.
        # If we can’t open a session or query fails, honor POLICY_FAIL_MODE.
        from app.core.db import SessionLocal
        try:
            with SessionLocal() as db:
                allowed = assess_risk(db, client_ip)
        except SQLAlchemyError as exc:
            log.warning("Policy DB session error; mode=%s; error=%s", POLICY_FAIL_MODE, exc)
            allowed = (POLICY_FAIL_MODE == "open")

        if not allowed:
            # Return a concise 403. We don’t leak internals; just enough to
            # tell the caller that policy denied the request.
            resp = JSONResponse({"detail": "Request denied by policy"}, status_code=HTTP_403_FORBIDDEN)
            return await resp(scope, receive, send)

        # Not risky? Hand off to the downstream ASGI app.
        return await self.app(scope, receive, send)
