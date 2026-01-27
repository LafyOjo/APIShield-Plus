"""create retention runs table

Revision ID: fffb3c4d5e6f
Revises: fffa2b7c1d4e
Create Date: 2026-01-23 17:05:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "fffb3c4d5e6f"
down_revision: Union[str, None] = "fffa2b7c1d4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "retention_runs",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
        ),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("event_retention_days", sa.Integer(), nullable=False),
        sa.Column("raw_ip_retention_days", sa.Integer(), nullable=False),
        sa.Column("behaviour_events_deleted", sa.Integer(), nullable=False),
        sa.Column("security_events_deleted", sa.Integer(), nullable=False),
        sa.Column("alerts_raw_ip_scrubbed", sa.Integer(), nullable=False),
        sa.Column("events_raw_ip_scrubbed", sa.Integer(), nullable=False),
        sa.Column("audit_logs_raw_ip_scrubbed", sa.Integer(), nullable=False),
        sa.Column("security_events_raw_ip_scrubbed", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_retention_runs_tenant_started_at",
        "retention_runs",
        ["tenant_id", "started_at"],
    )
    op.create_index("ix_retention_runs_tenant_id", "retention_runs", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_retention_runs_tenant_id", table_name="retention_runs")
    op.drop_index("ix_retention_runs_tenant_started_at", table_name="retention_runs")
    op.drop_table("retention_runs")
