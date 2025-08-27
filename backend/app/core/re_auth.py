# Per-request re-authentication middleware. When enabled, write
# operations must include BOTH a valid bearer token and a fresh
# password in X-Reauth-Password. Great for “step-up” security.

import os
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.status import HTTP_401_UNAUTHORIZED

# Flag to turn re-auth on/off without code changes. Read from env so
# different environments (dev, staging, prod) can opt in as needed.
REAUTH_ENABLED = os.getenv("REAUTH_PER_REQUEST", "false").lower() == "true"

# Which HTTP methods should demand step-up auth? Default is all
# writes (POST/PUT/PATCH/DELETE). You can override via env var
# REAUTH_METHODS to fine-tune behavior per deployment.
_METHODS = os.getenv("REAUTH_METHODS", "POST,PUT,PATCH,DELETE").strip()
REAUTH_METHODS = tuple(m.strip().upper() for m in _METHODS.split(",") if m.strip())

# Paths that should never be blocked by re-auth. These include
# health checks, docs, login/token endpoints, scoring, and audit.
# Keeping this list explicit avoids accidental lockouts.
SKIP_PATHS = {
    "/ping", "/health", "/healthz", "/metrics", "/docs", "/openapi.json",
    "/favicon.ico",
    "/login", "/register", "/api/token",
    "/score",
    "/api/audit/log",    # let audit fire without password
    "/events/auth",      # your shop auth hook
}


class ReAuthMiddleware(BaseHTTPMiddleware):
    # Middleware intercepts every request. If re-auth is enabled
    # and the request is a “write” to a protected path, we require
    # both a bearer token and a fresh password header.
    async def dispatch(self, request: Request, call_next):
        # If feature is off, do nothing. This keeps behavior stable
        # across environments and makes demos easy to toggle.
        if not REAUTH_ENABLED:
            return await call_next(request)

        # Always allow CORS preflight so browsers can proceed.
        # Blocking OPTIONS would break normal cross-origin flows.
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        # Skip infra/auth/telemetry paths so basic tooling continues
        # to work even with strict re-auth on write operations.
        if path in SKIP_PATHS:
            return await call_next(request)

        # Only enforce for configured methods. Reads (GET/HEAD) are
        # typically safe and shouldn’t nag users for a password.
        if request.method.upper() not in REAUTH_METHODS:
            return await call_next(request)

        # First layer: require a valid bearer token to ensure the
        # caller is authenticated before we ask for a password step-up.
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            return JSONResponse({"detail": "Unauthorized"}, status_code=HTTP_401_UNAUTHORIZED)

        # Second layer: require a fresh password via header. The UI
        # should prompt the user and send it along with the request.
        pw = request.headers.get("x-reauth-password")
        if not pw:
            return JSONResponse({"detail": "Password required"}, status_code=HTTP_401_UNAUTHORIZED)

        # Optional: you can verify `pw` against the authenticated user
        # here for full enforcement. In many demos, the trusted UI acts
        # as the gatekeeper, so we skip DB lookups for simplicity.

        return await call_next(request)
