"""add usage sampling counters

Revision ID: c1a2b3c4d5e7
Revises: c0a1b2c3d4e6
Create Date: 2026-02-06 09:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c1a2b3c4d5e7"
down_revision = "c0a1b2c3d4e6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tenant_usage",
        sa.Column("events_sampled_out", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.alter_column("tenant_usage", "events_sampled_out", server_default=None)


def downgrade():
    op.drop_column("tenant_usage", "events_sampled_out")
