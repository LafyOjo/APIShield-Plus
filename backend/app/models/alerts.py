# backend/app/models/alerts.py
from datetime import datetime, timedelta
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from app.core.db import Base


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alerts_tenant_time", "tenant_id", "timestamp"),)

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True)
    ip_address = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    total_fails = Column(Integer, nullable=False)
    detail = Column(String, nullable=True)

    @classmethod
    def one_minute_ago(cls) -> datetime:
        """Return timestamp representing one minute ago from now."""
        return datetime.utcnow() - timedelta(minutes=1)


# Pydantic schemas
class AlertBase(BaseModel):
    ip_address: str
    total_fails: int
    detail: Optional[str] = None


class AlertCreate(AlertBase):
    pass


class AlertRead(AlertBase):
    id: int
    timestamp: datetime

    class Config:
        orm_mode = True
