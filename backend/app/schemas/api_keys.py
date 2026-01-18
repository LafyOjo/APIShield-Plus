from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class APIKeyRead(BaseModel):
    id: int
    name: Optional[str]
    public_key: str
    created_at: datetime
    revoked_at: Optional[datetime]
    last_used_at: Optional[datetime]
    environment_id: int
    website_id: int

    class Config:
        orm_mode = True


class APIKeyCreate(BaseModel):
    name: Optional[str] = None
    environment_id: int


class APIKeyCreatedResponse(BaseModel):
    id: int
    public_key: str
    raw_secret: Optional[str] = None


class APIKeyCreateRequest(BaseModel):
    name: Optional[str] = None


class APIKeyCreatedWithSnippetResponse(BaseModel):
    id: int
    public_key: str
    created_at: datetime
    revoked_at: Optional[datetime]
    raw_secret: Optional[str] = None
    snippet: str


class APIKeyRevokeResponse(BaseModel):
    status: str
    revoked_at: datetime
