from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import (
    StatusComponentStatusEnum,
    StatusImpactEnum,
    StatusIncidentStatusEnum,
)


class StatusComponentRead(BaseModel):
    id: int
    key: str
    display_name: str
    current_status: StatusComponentStatusEnum
    last_updated_at: Optional[datetime]

    class Config:
        orm_mode = True


class StatusComponentUpdate(BaseModel):
    display_name: Optional[str] = None
    current_status: Optional[StatusComponentStatusEnum] = None


class StatusIncidentUpdateItem(BaseModel):
    timestamp: datetime
    message: str
    status: Optional[StatusIncidentStatusEnum] = None


class StatusIncidentRead(BaseModel):
    id: int
    status: StatusIncidentStatusEnum
    impact_level: StatusImpactEnum
    title: str
    components_affected: list[str]
    updates: list[StatusIncidentUpdateItem]
    is_published: bool
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime]

    class Config:
        orm_mode = True


class StatusIncidentCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    status: StatusIncidentStatusEnum = StatusIncidentStatusEnum.INVESTIGATING
    impact_level: StatusImpactEnum = StatusImpactEnum.MINOR
    components_affected: list[str] = Field(default_factory=list)
    message: Optional[str] = None
    is_published: bool = False


class StatusIncidentPatch(BaseModel):
    title: Optional[str] = Field(default=None, min_length=2, max_length=200)
    status: Optional[StatusIncidentStatusEnum] = None
    impact_level: Optional[StatusImpactEnum] = None
    components_affected: Optional[list[str]] = None
    is_published: Optional[bool] = None


class StatusIncidentUpdateCreate(BaseModel):
    message: str = Field(min_length=2, max_length=500)
    status: Optional[StatusIncidentStatusEnum] = None
