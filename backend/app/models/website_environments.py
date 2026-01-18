from sqlalchemy import Column, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.models.mixins import TimestampMixin


class WebsiteEnvironment(TimestampMixin, Base):
    __tablename__ = "website_environments"
    __table_args__ = (
        UniqueConstraint("website_id", "name", name="uq_website_env_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    website_id = Column(
        Integer,
        ForeignKey("websites.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name = Column(String, nullable=False)
    base_url = Column(String, nullable=True)
    status = Column(String, nullable=False, default="active")

    website = relationship("Website", back_populates="environments", lazy="selectin")
    api_keys = relationship("APIKey", back_populates="environment", lazy="selectin")
