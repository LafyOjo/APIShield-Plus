from typing import Optional

from pydantic import BaseModel


class WebsiteEnvironmentCreate(BaseModel):
    name: str
    base_url: Optional[str] = None


class WebsiteEnvironmentRead(BaseModel):
    id: int
    name: str
    base_url: Optional[str]
    status: str

    class Config:
        orm_mode = True


class WebsiteEnvironmentUpdate(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    status: Optional[str] = None
