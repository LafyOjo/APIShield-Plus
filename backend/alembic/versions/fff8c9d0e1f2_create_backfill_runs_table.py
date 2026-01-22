"""create backfill runs table

Revision ID: fff8c9d0e1f2
Revises: ffe7c8d9e0f1
Create Date: 2026-01-22 10:45:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "fff8c9d0e1f2"
down_revision: Union[str, None] = "ffe7c8d9e0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "backfill_runs",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
        ),
        sa.Column("job_name", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column(
            "last_id_processed",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_backfill_runs_job_name", "backfill_runs", ["job_name"])


def downgrade() -> None:
    op.drop_index("ix_backfill_runs_job_name", table_name="backfill_runs")
    op.drop_table("backfill_runs")
