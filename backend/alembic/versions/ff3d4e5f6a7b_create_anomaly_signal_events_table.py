"""create anomaly_signal_events table

Revision ID: ff3d4e5f6a7b
Revises: ff2c3d4e5f6a
Create Date: 2026-01-18 18:10:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ff3d4e5f6a7b"
down_revision: Union[str, None] = "ff2c3d4e5f6a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    json_type = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")
    op.create_table(
        "anomaly_signal_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("website_id", sa.Integer(), nullable=False),
        sa.Column("environment_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("signal_type", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("event_id", sa.String(), nullable=True),
        sa.Column("summary", json_type, nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["environment_id"], ["website_environments.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_anomaly_signals_tenant_created_at",
        "anomaly_signal_events",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_anomaly_signals_tenant_signal_type",
        "anomaly_signal_events",
        ["tenant_id", "signal_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_anomaly_signals_tenant_signal_type", table_name="anomaly_signal_events")
    op.drop_index("ix_anomaly_signals_tenant_created_at", table_name="anomaly_signal_events")
    op.drop_table("anomaly_signal_events")
