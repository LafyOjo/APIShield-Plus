"""create tenant usage table

Revision ID: 7e4d2c1f9a0b
Revises: 5c9d7a2e3b1f
Create Date: 2026-01-15 00:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7e4d2c1f9a0b"
down_revision: Union[str, None] = "5c9d7a2e3b1f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenant_usage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("period_start", sa.DateTime(), nullable=False),
        sa.Column("period_end", sa.DateTime(), nullable=True),
        sa.Column("events_ingested", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("storage_bytes", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "period_start", name="uq_tenant_usage_period"),
    )
    op.create_index(op.f("ix_tenant_usage_id"), "tenant_usage", ["id"], unique=False)
    op.create_index(op.f("ix_tenant_usage_tenant_id"), "tenant_usage", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_tenant_usage_period_start"), "tenant_usage", ["period_start"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tenant_usage_period_start"), table_name="tenant_usage")
    op.drop_index(op.f("ix_tenant_usage_tenant_id"), table_name="tenant_usage")
    op.drop_index(op.f("ix_tenant_usage_id"), table_name="tenant_usage")
    op.drop_table("tenant_usage")
