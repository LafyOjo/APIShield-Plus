from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, constr, validator

from app.models.enums import RoleEnum


class InviteCreate(BaseModel):
    email: EmailStr
    role: RoleEnum

    @validator("email")
    def normalize_email(cls, value: EmailStr) -> EmailStr:
        return EmailStr(value.lower())


class InviteRead(BaseModel):
    id: int
    tenant_id: int
    email: str
    role: RoleEnum
    expires_at: datetime
    accepted_at: Optional[datetime]
    created_at: datetime

    class Config:
        orm_mode = True


class InviteCreatedResponse(BaseModel):
    id: int
    email: str
    role: RoleEnum
    expires_at: datetime
    token: str


class InviteAccept(BaseModel):
    token: constr(min_length=8, strip_whitespace=True)


InviteAcceptRequest = InviteAccept
