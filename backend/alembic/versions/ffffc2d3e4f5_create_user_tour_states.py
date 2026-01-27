"""create user tour states

Revision ID: ffffc2d3e4f5
Revises: ffffb1c2d3e4
Create Date: 2026-01-25 19:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "ffffc2d3e4f5"
down_revision = "ffffb1c2d3e4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_tour_states",
        sa.Column("user_id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tours_completed_json", sa.JSON(), nullable=False),
        sa.Column("tours_dismissed_json", sa.JSON(), nullable=False),
        sa.Column("last_updated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_user_tour_states_user_id", "user_tour_states", ["user_id"])
    op.create_index("ix_user_tour_states_tenant_id", "user_tour_states", ["tenant_id"])


def downgrade():
    op.drop_index("ix_user_tour_states_tenant_id", table_name="user_tour_states")
    op.drop_index("ix_user_tour_states_user_id", table_name="user_tour_states")
    op.drop_table("user_tour_states")
