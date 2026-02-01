from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class OnboardingStateRead(BaseModel):
    tenant_id: int
    current_step: str
    completed_steps: list[str] = Field(default_factory=list)
    last_updated_at: Optional[datetime] = None
    verified_event_received_at: Optional[datetime] = None
    first_website_id: Optional[int] = None
    created_by_user_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class OnboardingStepComplete(BaseModel):
    step: str
    website_id: Optional[int] = None
    environment_id: Optional[int] = None


class FeatureLockedEvent(BaseModel):
    feature_key: str
    source: Optional[str] = None
    action: Optional[str] = None
