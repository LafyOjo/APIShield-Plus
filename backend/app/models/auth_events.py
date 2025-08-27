from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime

from app.core.db import Base


class AuthEvent(Base):
    __tablename__ = "auth_events"

    id = Column(Integer, primary_key=True, index=True)
    user = Column(String, nullable=True)
    action = Column(String, nullable=False)
    success = Column(Boolean, nullable=False, default=False)
    source = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
