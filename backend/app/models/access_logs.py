from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from app.core.db import Base


class AccessLog(Base):
    __tablename__ = "access_logs"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, nullable=True, index=True)
    path = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
