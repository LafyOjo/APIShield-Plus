from pydantic import BaseModel


class UserCreate(BaseModel):
    username: str
    password: str
    role: str | None = None


class UserRead(BaseModel):
    id: int
    username: str
    role: str

    class Config:
        orm_mode = True
