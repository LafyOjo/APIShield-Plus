from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, root_validator, validator

from app.models.enums import MembershipStatusEnum, RoleEnum


class MembershipRead(BaseModel):
    id: int
    tenant_id: int
    user_id: int
    role: RoleEnum
    status: MembershipStatusEnum
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class MembershipUserSummary(BaseModel):
    id: int
    email: str = Field(..., alias="username")
    display_name: Optional[str] = None

    class Config:
        orm_mode = True
        allow_population_by_field_name = True


class MembershipUserRead(MembershipRead):
    user: MembershipUserSummary


class MembershipCreate(BaseModel):
    user_id: Optional[int] = None
    email: Optional[EmailStr] = None
    role: RoleEnum

    @validator("email")
    def normalize_email(cls, value: Optional[EmailStr]) -> Optional[EmailStr]:
        if value is None:
            return value
        return value.lower()

    @root_validator(skip_on_failure=True)
    def require_user_or_email(cls, values):
        user_id = values.get("user_id")
        email = values.get("email")
        if (user_id is None) == (email is None):
            raise ValueError("Provide exactly one of user_id or email.")
        return values


class MembershipUpdate(BaseModel):
    role: RoleEnum


class MemberUser(BaseModel):
    id: int
    email: Optional[str] = None
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None


class MemberMembership(BaseModel):
    id: int
    role: RoleEnum
    status: MembershipStatusEnum
    created_at: datetime


class MemberListItem(BaseModel):
    user: MemberUser
    membership: MemberMembership


class MemberDeleteResponse(BaseModel):
    success: bool
