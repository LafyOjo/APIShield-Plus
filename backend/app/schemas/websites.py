from datetime import datetime
import re
from typing import Optional

from pydantic import BaseModel, constr, validator

from app.models.enums import WebsiteStatusEnum


DisplayNameStr = constr(min_length=1, max_length=80, strip_whitespace=True)
_DOMAIN_INVALID_RE = re.compile(r"[/?#]")


class WebsiteCreate(BaseModel):
    domain: str
    display_name: Optional[DisplayNameStr] = None

    @validator("domain")
    def validate_domain(cls, value: str) -> str:
        raw = value.strip()
        if "://" in raw:
            raise ValueError("domain must not include a protocol")
        if _DOMAIN_INVALID_RE.search(raw):
            raise ValueError("domain must not include a path, query, or fragment")
        normalized = raw.lower()
        if not normalized:
            raise ValueError("domain is required")
        return normalized


class WebsiteRead(BaseModel):
    id: int
    domain: str
    display_name: Optional[str]
    status: WebsiteStatusEnum
    created_at: datetime

    class Config:
        orm_mode = True


class WebsiteAdminRead(WebsiteRead):
    deleted_at: Optional[datetime] = None


class WebsiteUpdate(BaseModel):
    display_name: Optional[DisplayNameStr] = None
    status: Optional[WebsiteStatusEnum] = None
