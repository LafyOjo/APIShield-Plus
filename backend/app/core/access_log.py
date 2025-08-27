# This middleware quietly watches every incoming HTTP request and, after
# the route has done its job, logs a tiny breadcrumb: which user (if any)
# touched which path. I run this in a `finally` block so we record even
# when handlers raise or responses error out. It’s lightweight, readable,
# and gives us a simple audit trail without sprinkling logging everywhere.

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

# I only decode the token locally to fetch the username claim (sub). This isn’t
# about authorization; it’s purely for tagging the access log with “who”
# initiated the call. If there’s no valid token, I just log `None` and move on.
from app.core.security import decode_access_token

# I grab a short-lived DB session right here in the middleware so the logging
# doesn’t depend on individual routes. Using SessionLocal directly keeps the
# cross-cutting concern (access logging) nicely centralized in one place.
from app.core.db import SessionLocal
from app.crud.access_logs import create_access_log


class AccessLogMiddleware(BaseHTTPMiddleware):
    """
    # Why a middleware?
    # Placing this logic in middleware means every request is consistently
    # captured, regardless of which endpoint it hits. Routes stay focused on
    # business logic, while this “after the fact” logger quietly records who
    # touched what. Less duplication, fewer mistakes, and easy to turn off.
    """

    async def dispatch(self, request: Request, call_next):
        """
        # Dispatch flow in a nutshell:
        # 1) Let the request pass through to the actual route handler.
        # 2) No matter what happens (success, error, exception), pop into
        #    the `finally` block to log access details.
        # 3) We only decode the token to extract the username claim and
        #    then write a single row with username + path.
        """
        try:
            # Let the main application do its work. We don’t want logging
            # to alter behavior or swallow exceptions — just observe.
            response = await call_next(request)
            return response
        finally:
            # I don’t want logging to cause failures, so this is all “best effort.”
            # If there’s an Authorization header and it looks like a Bearer token,
            # I try to decode it and read the `sub` claim. If decoding fails for
            # any reason (expired, malformed, tampered), I just fall back to None.
            username = None
            auth = request.headers.get("Authorization")
            if auth and auth.startswith("Bearer "):
                token = auth.split()[1]
                try:
                    payload = decode_access_token(token)
                    username = payload.get("sub")
                except Exception:
                    # Bad token? No problem — we still log the path with no user.
                    username = None

            # I open a tiny, short-lived DB session purely for the log write.
            # This keeps the middleware self-contained and avoids relying on
            # route-scoped sessions. The log itself is intentionally minimal:
            # who (if known) and which path — perfect for dashboards & audits.
            with SessionLocal() as db:
                create_access_log(db, username, request.url.path)
