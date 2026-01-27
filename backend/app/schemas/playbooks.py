from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class PlaybookCodeSnippet(BaseModel):
    language: Optional[str] = None
    snippet: str


class PlaybookSection(BaseModel):
    title: str
    context: Optional[str] = None
    steps: list[str] = []
    code_snippets: list[PlaybookCodeSnippet] = []
    verification_steps: list[str] = []
    rollback_steps: list[str] = []
    risk_level: Optional[str] = None


class RemediationPlaybookRead(BaseModel):
    id: int
    incident_id: int
    website_id: Optional[int] = None
    environment_id: Optional[int] = None
    stack_type: str
    status: str
    version: int
    sections: list[PlaybookSection]
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
