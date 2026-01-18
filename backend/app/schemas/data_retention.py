from pydantic import BaseModel


class DataRetentionRead(BaseModel):
    event_type: str
    days: int

    class Config:
        orm_mode = True


class DataRetentionUpdate(BaseModel):
    event_type: str
    days: int
