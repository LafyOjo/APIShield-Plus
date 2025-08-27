from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from app.core.db import Base


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, nullable=True, index=True)
    action = Column(String, nullable=False)
    success = Column(Boolean, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
