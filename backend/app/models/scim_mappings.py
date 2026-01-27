from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint

from app.core.db import Base
from app.core.time import utcnow
from app.models.mixins import TimestampMixin


class SCIMExternalUserMap(TimestampMixin, Base):
    __tablename__ = "scim_external_user_maps"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "scim_user_id",
            name="uq_scim_user_map_tenant_scim_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "user_id",
            name="uq_scim_user_map_tenant_user",
        ),
        Index("ix_scim_user_map_tenant", "tenant_id"),
    )

    id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        index=True,
        autoincrement=True,
    )
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False)
    scim_user_id = Column(String, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class SCIMExternalGroupMap(TimestampMixin, Base):
    __tablename__ = "scim_external_group_maps"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "scim_group_id",
            name="uq_scim_group_map_tenant_scim_id",
        ),
        Index("ix_scim_group_map_tenant", "tenant_id"),
    )

    id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        index=True,
        autoincrement=True,
    )
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False)
    scim_group_id = Column(String, nullable=False)
    tenant_role = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)
