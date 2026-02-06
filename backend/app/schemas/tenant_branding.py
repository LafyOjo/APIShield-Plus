from datetime import datetime
from typing import Optional
from urllib.parse import urlparse
import re

from pydantic import BaseModel, Field, validator

from app.core.branding import ALLOWED_BADGE_BRANDING_MODES, normalize_badge_branding_mode


_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{6})$")


class TenantBrandingRead(BaseModel):
    tenant_id: int
    is_enabled: bool
    brand_name: Optional[str] = None
    logo_url: Optional[str] = None
    primary_color: Optional[str] = None
    accent_color: Optional[str] = None
    custom_domain: Optional[str] = None
    domain_verified_at: Optional[datetime] = None
    badge_branding_mode: str
    updated_at: datetime
    verification_txt_name: Optional[str] = None
    verification_txt_value: Optional[str] = None

    class Config:
        orm_mode = True


class TenantBrandingUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    brand_name: Optional[str] = Field(default=None, max_length=120)
    logo_url: Optional[str] = None
    primary_color: Optional[str] = None
    accent_color: Optional[str] = None
    custom_domain: Optional[str] = None
    badge_branding_mode: Optional[str] = None

    @validator("logo_url")
    def validate_logo_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        cleaned = value.strip()
        if not cleaned:
            return None
        parsed = urlparse(cleaned)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("logo_url must be a valid http(s) URL")
        return cleaned

    @validator("primary_color", "accent_color")
    def validate_colors(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        cleaned = value.strip()
        if not cleaned:
            return None
        if not _COLOR_RE.match(cleaned):
            raise ValueError("Colors must be in #RRGGBB format")
        return cleaned.lower()

    @validator("custom_domain")
    def validate_custom_domain(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        cleaned = value.strip().lower()
        if not cleaned:
            return None
        if cleaned.startswith("http://") or cleaned.startswith("https://"):
            raise ValueError("custom_domain should not include a scheme")
        if "/" in cleaned or "?" in cleaned or "#" in cleaned:
            raise ValueError("custom_domain must be a bare domain")
        return cleaned

    @validator("badge_branding_mode")
    def validate_badge_branding_mode(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = normalize_badge_branding_mode(value)
        if normalized not in ALLOWED_BADGE_BRANDING_MODES:
            raise ValueError("Unsupported badge branding mode")
        return normalized
