"""
Security headers middleware for safer HTTP defaults.
"""

from __future__ import annotations

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings


def _build_hsts_value() -> str:
    value = f"max-age={int(settings.HSTS_MAX_AGE)}"
    if settings.HSTS_INCLUDE_SUBDOMAINS:
        value = f"{value}; includeSubDomains"
    if settings.HSTS_PRELOAD:
        value = f"{value}; preload"
    return value


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        if not settings.SECURITY_HEADERS_ENABLED:
            return response

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", settings.X_FRAME_OPTIONS)
        response.headers.setdefault("Referrer-Policy", settings.REFERRER_POLICY)
        if settings.CSP_DEFAULT:
            response.headers.setdefault("Content-Security-Policy", settings.CSP_DEFAULT)

        forwarded_proto = request.headers.get("X-Forwarded-Proto", "")
        is_https = request.url.scheme == "https" or forwarded_proto.lower() == "https"
        if is_https:
            response.headers.setdefault("Strict-Transport-Security", _build_hsts_value())

        return response
