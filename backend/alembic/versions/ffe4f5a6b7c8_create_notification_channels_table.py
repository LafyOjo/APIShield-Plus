"""create notification channels table

Revision ID: ffe4f5a6b7c8
Revises: ffd3e4f5f6f7
Create Date: 2026-01-21 12:15:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ffe4f5a6b7c8"
down_revision: Union[str, None] = "ffd3e4f5f6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    json_type = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")
    op.create_table(
        "notification_channels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("config_public_json", json_type, nullable=True),
        sa.Column("config_secret_enc", sa.Text(), nullable=True),
        sa.Column("categories_allowed", json_type, nullable=True),
        sa.Column("last_tested_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_notification_channels_tenant_type_enabled",
        "notification_channels",
        ["tenant_id", "type", "is_enabled"],
    )


def downgrade() -> None:
    op.drop_index("ix_notification_channels_tenant_type_enabled", table_name="notification_channels")
    op.drop_table("notification_channels")
