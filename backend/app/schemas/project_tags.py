from typing import Optional

from pydantic import BaseModel


class ProjectTagCreate(BaseModel):
    name: str
    color: Optional[str] = None


class ProjectTagRead(BaseModel):
    id: int
    name: str
    color: Optional[str]

    class Config:
        orm_mode = True
