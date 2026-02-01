"""create growth snapshots

Revision ID: fffff0c1d2e3
Revises: fffff9b0c2d3
Create Date: 2026-01-31 10:12:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "fffff0c1d2e3"
down_revision = "fffff9b0c2d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "growth_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("signups", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("activated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("onboarding_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_incident", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_prescription", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("upgraded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("churned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_time_to_first_event_seconds", sa.Float(), nullable=True),
        sa.Column("funnel_json", sa.JSON(), nullable=True),
        sa.Column("cohort_json", sa.JSON(), nullable=True),
        sa.Column("paywall_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("snapshot_date", name="uq_growth_snapshot_date"),
    )
    op.create_index("ix_growth_snapshot_date", "growth_snapshots", ["snapshot_date"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_growth_snapshot_date", table_name="growth_snapshots")
    op.drop_table("growth_snapshots")
