"""add usage storage counters

Revision ID: c0a1b2c3d4e5
Revises: fffffc1d2e3f
Create Date: 2026-02-05 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c0a1b2c3d4e5"
down_revision = "fffffc1d2e3f"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tenant_usage",
        sa.Column("raw_events_stored", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "tenant_usage",
        sa.Column("aggregate_rows_stored", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.alter_column("tenant_usage", "raw_events_stored", server_default=None)
    op.alter_column("tenant_usage", "aggregate_rows_stored", server_default=None)


def downgrade():
    op.drop_column("tenant_usage", "aggregate_rows_stored")
    op.drop_column("tenant_usage", "raw_events_stored")
