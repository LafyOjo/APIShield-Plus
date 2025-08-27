from sqlalchemy import Column, Integer, Boolean
from app.core.db import Base


class Policy(Base):
    __tablename__ = "policies"

    id = Column(Integer, primary_key=True, index=True)
    failed_attempts_limit = Column(Integer, nullable=False)
    mfa_required = Column(Boolean, nullable=False, default=False)
    geo_fencing_enabled = Column(Boolean, nullable=False, default=False)
