from sqlalchemy import Column, DateTime, event

from app.core.time import utcnow


class TimestampMixin:
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    @staticmethod
    def _touch_updated_at(mapper, connection, target) -> None:
        target.updated_at = utcnow()

    @classmethod
    def __declare_last__(cls) -> None:
        event.listen(cls, "before_update", cls._touch_updated_at)
