from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DataExportConfigUpsert(BaseModel):
    target_type: str
    target_config: Optional[dict] = None
    schedule: Optional[str] = "daily"
    datasets_enabled: Optional[list[str]] = None
    format: Optional[str] = "jsonl.gz"
    is_enabled: Optional[bool] = True


class DataExportConfigUpdate(BaseModel):
    target_type: Optional[str] = None
    target_config: Optional[dict] = None
    schedule: Optional[str] = None
    datasets_enabled: Optional[list[str]] = None
    format: Optional[str] = None
    is_enabled: Optional[bool] = None


class DataExportConfigRead(BaseModel):
    id: int
    tenant_id: int
    is_enabled: bool
    target_type: str
    schedule: str
    datasets_enabled: list[str]
    format: str
    last_run_at: Optional[datetime]
    last_error: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
