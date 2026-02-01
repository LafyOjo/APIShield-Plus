from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class MarketplaceTemplateRead(BaseModel):
    id: int
    template_type: str
    title: str
    description: str
    stack_type: Optional[str] = None
    tags: list[str] = []
    content_json: dict[str, Any] = {}
    source: str
    status: str
    safety_notes: Optional[str] = None
    downloads_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class MarketplaceTemplateCreate(BaseModel):
    template_type: str
    title: str
    description: str
    stack_type: Optional[str] = None
    tags: list[str] = []
    content_json: dict[str, Any]


class MarketplaceTemplateUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    stack_type: Optional[str] = None
    tags: Optional[list[str]] = None
    content_json: Optional[dict[str, Any]] = None
    status: Optional[str] = None
    source: Optional[str] = None
    safety_notes: Optional[str] = None


class MarketplaceImportRequest(BaseModel):
    incident_id: Optional[int] = None


class MarketplaceImportResponse(BaseModel):
    template_id: int
    import_event_id: int
    playbook_id: Optional[int] = None
    preset_id: Optional[int] = None
    rule_ids: list[int] = []
