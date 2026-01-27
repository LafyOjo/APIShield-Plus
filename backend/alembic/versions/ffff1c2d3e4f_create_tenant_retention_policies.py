"""create tenant retention policies table

Revision ID: ffff1c2d3e4f
Revises: ffff0b1c2d3e
Create Date: 2026-01-24 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ffff1c2d3e4f"
down_revision: Union[str, None] = "ffff0b1c2d3e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenant_retention_policies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("dataset_key", sa.String(), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("is_legal_hold_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("legal_hold_reason", sa.Text(), nullable=True),
        sa.Column("legal_hold_enabled_at", sa.DateTime(), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("tenant_id", "dataset_key", name="uq_tenant_retention_dataset"),
    )
    op.create_index(
        "ix_tenant_retention_policies_tenant_id",
        "tenant_retention_policies",
        ["tenant_id"],
    )
    op.create_index(
        "ix_tenant_retention_tenant_dataset",
        "tenant_retention_policies",
        ["tenant_id", "dataset_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_tenant_retention_tenant_dataset", table_name="tenant_retention_policies")
    op.drop_index("ix_tenant_retention_policies_tenant_id", table_name="tenant_retention_policies")
    op.drop_table("tenant_retention_policies")
