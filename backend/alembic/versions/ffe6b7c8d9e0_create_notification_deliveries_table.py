"""create notification deliveries table

Revision ID: ffe6b7c8d9e0
Revises: ffe5a6b7c8d9
Create Date: 2026-01-21 14:10:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ffe6b7c8d9e0"
down_revision: Union[str, None] = "ffe5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    json_type = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")
    op.create_table(
        "notification_deliveries",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
        ),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("rule_id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("dedupe_key", sa.String(), nullable=False),
        sa.Column("payload_json", json_type, nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["rule_id"], ["notification_rules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["channel_id"], ["notification_channels.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "tenant_id",
            "dedupe_key",
            name="uq_notification_deliveries_tenant_dedupe",
        ),
    )
    op.create_index(
        "ix_notification_deliveries_tenant_status_created",
        "notification_deliveries",
        ["tenant_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_notification_deliveries_tenant_status_created",
        table_name="notification_deliveries",
    )
    op.drop_table("notification_deliveries")
