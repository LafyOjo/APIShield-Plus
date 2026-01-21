"""create notification rules table

Revision ID: ffe5a6b7c8d9
Revises: ffe4f5a6b7c8
Create Date: 2026-01-21 13:05:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ffe5a6b7c8d9"
down_revision: Union[str, None] = "ffe4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    json_type = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")
    op.create_table(
        "notification_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("trigger_type", sa.String(), nullable=False),
        sa.Column("filters_json", json_type, nullable=True),
        sa.Column("thresholds_json", json_type, nullable=True),
        sa.Column("quiet_hours_json", json_type, nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_notification_rules_tenant_trigger",
        "notification_rules",
        ["tenant_id", "trigger_type"],
    )
    op.create_index(
        "ix_notification_rules_tenant_enabled",
        "notification_rules",
        ["tenant_id", "is_enabled"],
    )

    op.create_table(
        "notification_rule_channels",
        sa.Column("rule_id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["rule_id"], ["notification_rules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["channel_id"], ["notification_channels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("rule_id", "channel_id"),
    )
    op.create_index(
        "ix_notification_rule_channels_channel",
        "notification_rule_channels",
        ["channel_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_notification_rule_channels_channel", table_name="notification_rule_channels")
    op.drop_table("notification_rule_channels")
    op.drop_index("ix_notification_rules_tenant_enabled", table_name="notification_rules")
    op.drop_index("ix_notification_rules_tenant_trigger", table_name="notification_rules")
    op.drop_table("notification_rules")
