"""
Standard request metadata capture helpers.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import Request


def resolve_request_meta(
    request: Request | None = None,
    request_meta: dict[str, str | None] | None = None,
) -> dict[str, str | None] | None:
    if request_meta is not None:
        return request_meta
    if request is None:
        return None
    return getattr(request.state, "request_meta", None)


def build_request_meta(
    request: Request,
    *,
    request_id: str | None = None,
    client_ip: str | None = None,
) -> dict[str, str | None]:
    resolved_request_id = (
        request_id
        or getattr(request.state, "request_id", None)
        or request.headers.get("X-Request-ID")
        or str(uuid4())
    )
    return {
        "request_id": resolved_request_id,
        "client_ip": client_ip,
        "user_agent": request.headers.get("User-Agent"),
        "path": request.url.path,
        "method": request.method,
        "referer": request.headers.get("Referer"),
        "accept_language": request.headers.get("Accept-Language"),
        "origin": request.headers.get("Origin"),
    }
