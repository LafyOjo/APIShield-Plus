# This middleware ensures that every incoming request either
# presents a valid API key or belongs to a pre-approved endpoint.
# Requests without the right key get logged and rejected with 401.

import os
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.status import HTTP_401_UNAUTHORIZED

from app.core.db import SessionLocal
from app.api.score import record_attempt

# Grab the configured Zero Trust API key from environment.
# If not set, the middleware effectively runs in “open mode”
# and won’t block anything.
API_KEY = os.getenv("ZERO_TRUST_API_KEY")

# These are paths that can bypass the Zero Trust check entirely.
# Think of them as “public” or “infra” endpoints where requiring
# an API key would break basic app usability or monitoring.
ALLOWED_PATHS = {
    "/ping",
    "/login",
    "/register",
    "/api/token",
    "/openapi.json",
    "/docs",
    "/docs/oauth2-redirect",
    "/metrics",
    "/api/audit/log",  # logs need to flow even if API key is missing
}


class ZeroTrustMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Step 1: Always let CORS preflights (OPTIONS requests) go.
        # These aren’t real user requests and shouldn’t be blocked.
        if request.method == "OPTIONS":
            return await call_next(request)

        # Step 2: If API_KEY isn’t set, we treat it as “disabled”.
        # That way local/dev environments can run without hassle.
        if not API_KEY:
            return await call_next(request)

        # Step 3: Allow public paths to bypass API key enforcement.
        # Without this, even login and docs would fail with 401.
        if request.url.path in {"/ping", "/login", "/register", "/api/token"}:
            return await call_next(request)

        # Step 4: Special-case the audit log route. Audit must log
        # even failed or pre-auth attempts, so we never block it.
        if request.url.path == "/api/audit/log":
            return await call_next(request)

        # Step 5: Enforce the API key by checking the X-API-Key
        # header. If it’s wrong or missing, log the incident and
        # return 401 Unauthorized to the caller.
        header = request.headers.get("X-API-Key")
        if header != API_KEY:
            client_ip = request.client.host if request.client else "unknown"
            with SessionLocal() as db:
                record_attempt(db, client_ip, False, detail="Invalid API key")
            return JSONResponse({"detail": "Invalid API key"}, status_code=401)

        # Step 6: If all checks pass, the request is allowed
        # through and the next middleware/endpoint can handle it.
        return await call_next(request)
