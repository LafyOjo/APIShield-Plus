from typing import Optional

from pydantic import BaseModel


class UserProfileRead(BaseModel):
    display_name: Optional[str]
    avatar_url: Optional[str]
    timezone: Optional[str]
    email_opt_out: Optional[bool] = False

    class Config:
        orm_mode = True


class UserProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    timezone: Optional[str] = None
    email_opt_out: Optional[bool] = None
