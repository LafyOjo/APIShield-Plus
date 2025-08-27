from datetime import datetime
from pydantic import BaseModel


class AccessLogRead(BaseModel):
    id: int
    username: str | None = None
    path: str
    timestamp: datetime

    class Config:
        orm_mode = True
