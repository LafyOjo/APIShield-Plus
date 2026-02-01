from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel, validator

from app.core.badges import ALLOWED_BADGE_STYLES, normalize_style


class TrustBadgeConfigRead(BaseModel):
    id: int
    tenant_id: int
    website_id: int
    is_enabled: bool
    style: str
    show_score: bool
    show_branding: bool
    clickthrough_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    script_url: Optional[str] = None
    script_tag: Optional[str] = None

    class Config:
        orm_mode = True


class TrustBadgeConfigUpdate(BaseModel):
    website_id: int
    is_enabled: Optional[bool] = None
    style: Optional[str] = None
    show_score: Optional[bool] = None
    show_branding: Optional[bool] = None
    clickthrough_url: Optional[str] = None

    @validator("style")
    def validate_style(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = normalize_style(value)
        if normalized not in ALLOWED_BADGE_STYLES:
            raise ValueError("Unsupported badge style")
        return normalized

    @validator("clickthrough_url")
    def validate_clickthrough_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        cleaned = value.strip()
        if not cleaned:
            return None
        parsed = urlparse(cleaned)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("clickthrough_url must be a valid http(s) URL")
        return cleaned
