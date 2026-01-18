from sqlalchemy import Column, DateTime, Enum, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.models.enums import RoleEnum
from app.models.mixins import TimestampMixin


class Invite(TimestampMixin, Base):
    __tablename__ = "invites"
    __table_args__ = (
        Index("ix_invites_tenant_email", "tenant_id", "email"),
        Index("ix_invites_tenant_expires_at", "tenant_id", "expires_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    email = Column(String, nullable=False)
    role = Column(
        Enum(
            RoleEnum,
            name="invite_role_enum",
            native_enum=False,
            validate_strings=True,
        ),
        nullable=False,
    )
    token_hash = Column(String, nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=False)
    accepted_at = Column(DateTime, nullable=True)
    created_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    tenant = relationship("Tenant", back_populates="invites", lazy="selectin")
    created_by = relationship(
        "User",
        back_populates="created_invites",
        foreign_keys=[created_by_user_id],
        lazy="selectin",
    )
