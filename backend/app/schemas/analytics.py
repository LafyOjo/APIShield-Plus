from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, validator

from app.core.event_types import normalize_event_type, normalize_path


class SessionListItem(BaseModel):
    session_id: str
    website_id: int
    environment_id: int
    started_at: datetime
    last_seen_at: datetime
    entry_path: Optional[str] = None
    exit_path: Optional[str] = None
    page_views: int
    event_count: int
    ip_hash: Optional[str] = None
    country_code: Optional[str] = None

    class Config:
        orm_mode = True


class SessionDetail(SessionListItem):
    duration_seconds: int


class SessionEventItem(BaseModel):
    event_id: str
    event_type: str
    event_ts: datetime
    url: str
    path: Optional[str] = None
    referrer: Optional[str] = None
    session_id: Optional[str] = None
    meta: Optional[dict] = None

    class Config:
        orm_mode = True


class FunnelStepInput(BaseModel):
    type: str
    path: Optional[str] = None

    @validator("type")
    def validate_type(cls, value: str) -> str:
        return normalize_event_type(value)

    @validator("path")
    def validate_path(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return normalize_path(value)


class FunnelRequest(BaseModel):
    website_id: int
    env_id: int
    from_ts: Optional[datetime] = Field(None, alias="from")
    to_ts: Optional[datetime] = Field(None, alias="to")
    steps: list[FunnelStepInput]

    @validator("steps")
    def validate_steps(cls, value: list[FunnelStepInput]) -> list[FunnelStepInput]:
        if not value:
            raise ValueError("At least one step is required.")
        if len(value) > 10:
            raise ValueError("Funnel step limit exceeded.")
        return value

    class Config:
        allow_population_by_field_name = True


class FunnelStepResult(BaseModel):
    type: str
    path: Optional[str] = None
    count: int
    dropoff: int
    conversion_to_next: Optional[float] = None


class FunnelResponse(BaseModel):
    steps: list[FunnelStepResult]
    total_sessions: int
