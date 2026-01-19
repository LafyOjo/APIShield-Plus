from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit


ALLOWED_BROWSER_EVENT_TYPES = {
    "page_view",
    "click",
    "scroll",
    "rage_click",
    "form_submit",
    "error",
    "performance",
}

DROP_URL_QUERY = True
MAX_META_BYTES = 4096
SESSION_ID_MAX_LENGTH = 128
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def normalize_event_type(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in ALLOWED_BROWSER_EVENT_TYPES:
        raise ValueError("Unsupported event type.")
    return normalized


def normalize_url(value: str, *, drop_query: bool = DROP_URL_QUERY) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL must include http/https scheme and host.")
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    query = "" if drop_query else parsed.query
    return urlunsplit((scheme, netloc, path, query, ""))


def normalize_path(value: str) -> str:
    parsed = urlsplit(value)
    path = parsed.path or "/"
    if not path.startswith("/"):
        raise ValueError("path must start with '/'")
    return path


def clamp_meta(meta: dict[str, Any] | None, max_bytes: int = MAX_META_BYTES) -> dict[str, Any] | None:
    if meta is None:
        return None
    try:
        payload = json.dumps(meta, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    except (TypeError, ValueError):
        return {}
    if len(payload) <= max_bytes:
        return meta
    return {}
