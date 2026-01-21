from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, validator

from app.core.event_types import clamp_meta, normalize_path
from app.security.taxonomy import SeverityEnum, normalize_event_type


class IngestSecurityEvent(BaseModel):
    ts: Optional[datetime] = None
    event_type: str
    severity: str
    request_path: Optional[str] = None
    method: Optional[str] = None
    status_code: Optional[int] = Field(None, ge=100, le=599)
    user_identifier: Optional[str] = None
    session_id: Optional[str] = None
    meta: Optional[dict[str, Any]] = None
    source: Optional[str] = None

    @validator("event_type")
    def validate_event_type(cls, value: str) -> str:
        return normalize_event_type(value).value

    @validator("severity")
    def validate_severity(cls, value: str) -> str:
        try:
            return SeverityEnum(value.strip().lower()).value
        except ValueError as exc:
            raise ValueError("Invalid severity.") from exc

    @validator("request_path")
    def validate_path(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return normalize_path(value)

    @validator("method")
    def normalize_method(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = value.strip().upper()
        if not normalized:
            return None
        return normalized

    @validator("source")
    def normalize_source(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = value.strip().lower()
        if not normalized:
            return None
        if len(normalized) > 32:
            raise ValueError("source exceeds maximum length.")
        return normalized

    @validator("meta")
    def clamp_meta_payload(cls, value: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        return clamp_meta(value)


class IngestSecurityResponse(BaseModel):
    ok: bool
    received_at: datetime
