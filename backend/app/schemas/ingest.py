from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, validator

from app.core.event_types import (
    SESSION_ID_MAX_LENGTH,
    SESSION_ID_PATTERN,
    clamp_meta,
    normalize_event_type,
    normalize_path,
    normalize_url,
)
from app.stack.constants import STACK_HINT_KEYS


class IngestBrowserEvent(BaseModel):
    event_id: str
    ts: datetime
    type: str
    url: str
    path: Optional[str] = None
    referrer: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    meta: Optional[dict[str, Any]] = None
    stack_hints: Optional[dict[str, bool]] = None

    @validator("event_id")
    def validate_event_id(cls, value: str) -> str:
        try:
            return str(UUID(str(value)))
        except (TypeError, ValueError) as exc:
            raise ValueError("event_id must be a valid UUID.") from exc

    @validator("type")
    def validate_type(cls, value: str) -> str:
        return normalize_event_type(value)

    @validator("url")
    def validate_url(cls, value: str) -> str:
        return normalize_url(value)

    @validator("path")
    def validate_path(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return normalize_path(value)

    @validator("session_id")
    def validate_session_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if len(value) > SESSION_ID_MAX_LENGTH:
            raise ValueError("session_id exceeds maximum length.")
        if not SESSION_ID_PATTERN.match(value):
            raise ValueError("session_id has invalid characters.")
        return value

    @validator("meta")
    def clamp_meta_payload(cls, value: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        return clamp_meta(value)

    @validator("stack_hints")
    def clamp_stack_hints(cls, value: Optional[dict[str, Any]]) -> Optional[dict[str, bool]]:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValueError("stack_hints must be a dictionary.")
        cleaned: dict[str, bool] = {}
        for key, raw in value.items():
            if key not in STACK_HINT_KEYS:
                continue
            if isinstance(raw, bool):
                cleaned[key] = raw
            else:
                cleaned[key] = bool(raw)
        return cleaned or None


class IngestBrowserResponse(BaseModel):
    ok: bool
    received_at: datetime
    request_id: Optional[str] = None
    deduped: bool = False
    accepted: Optional[int] = None
    dropped: Optional[int] = None
    deduped_count: Optional[int] = None
    sampled_out: Optional[int] = None


class IngestBrowserBatch(BaseModel):
    events: list[IngestBrowserEvent]
