"""create data retention policies table

Revision ID: 9f1a0b2c3d4e
Revises: 7e4d2c1f9a0b
Create Date: 2026-01-15 01:10:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9f1a0b2c3d4e"
down_revision: Union[str, None] = "7e4d2c1f9a0b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "data_retention_policies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "event_type", name="uq_retention_tenant_event"),
    )
    op.create_index(op.f("ix_data_retention_policies_id"), "data_retention_policies", ["id"], unique=False)
    op.create_index(
        op.f("ix_data_retention_policies_tenant_id"),
        "data_retention_policies",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_data_retention_policies_event_type"),
        "data_retention_policies",
        ["event_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_data_retention_policies_event_type"), table_name="data_retention_policies")
    op.drop_index(op.f("ix_data_retention_policies_tenant_id"), table_name="data_retention_policies")
    op.drop_index(op.f("ix_data_retention_policies_id"), table_name="data_retention_policies")
    op.drop_table("data_retention_policies")
