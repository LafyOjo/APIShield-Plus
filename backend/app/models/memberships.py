from sqlalchemy import Column, Enum, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.models.enums import MembershipStatusEnum, RoleEnum
from app.models.mixins import TimestampMixin


class Membership(TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_membership_user_tenant"),
        Index("ix_memberships_tenant_id", "tenant_id"),
        Index("ix_memberships_tenant_role", "tenant_id", "role"),
        Index("ix_memberships_user_id", "user_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    role = Column(
        Enum(
            RoleEnum,
            name="membership_role_enum",
            native_enum=False,
            validate_strings=True,
        ),
        nullable=False,
    )
    status = Column(
        Enum(
            MembershipStatusEnum,
            name="membership_status_enum",
            native_enum=False,
            validate_strings=True,
        ),
        nullable=False,
        default=MembershipStatusEnum.ACTIVE,
    )
    created_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    tenant = relationship("Tenant", back_populates="memberships", lazy="selectin")
    user = relationship(
        "User",
        back_populates="memberships",
        foreign_keys=[user_id],
        lazy="selectin",
    )
    created_by = relationship(
        "User",
        back_populates="created_memberships",
        foreign_keys=[created_by_user_id],
        lazy="selectin",
    )
