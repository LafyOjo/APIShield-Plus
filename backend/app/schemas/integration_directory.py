from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class IntegrationListingRead(BaseModel):
    key: str
    name: str
    category: str
    description: str
    docs_url: Optional[str] = None
    install_type: str
    is_featured: bool
    plan_required: Optional[str] = None
    install_url: Optional[str] = None
    copy_payload: Optional[str] = None
    stack_types: list[str] = []
    recommended: bool = False
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class IntegrationInstallEventCreate(BaseModel):
    integration_key: str
    website_id: Optional[int] = None
    method: str
    metadata: Optional[dict[str, Any]] = None


class IntegrationInstallEventRead(BaseModel):
    id: int
    tenant_id: int
    website_id: Optional[int] = None
    integration_key: str
    installed_at: datetime
    method: str

    class Config:
        orm_mode = True
