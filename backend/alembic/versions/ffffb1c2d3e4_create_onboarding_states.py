"""create onboarding states

Revision ID: ffffb1c2d3e4
Revises: ffffa0b1c2d3
Create Date: 2026-01-25 19:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "ffffb1c2d3e4"
down_revision = "ffffa0b1c2d3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "onboarding_states",
        sa.Column("tenant_id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("current_step", sa.String(), nullable=False),
        sa.Column("completed_steps_json", sa.JSON(), nullable=False),
        sa.Column("last_updated_at", sa.DateTime(), nullable=True),
        sa.Column("verified_event_received_at", sa.DateTime(), nullable=True),
        sa.Column("first_website_id", sa.Integer(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["first_website_id"], ["websites.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_onboarding_states_tenant_id", "onboarding_states", ["tenant_id"])
    op.create_index("ix_onboarding_states_first_website_id", "onboarding_states", ["first_website_id"])
    op.create_index("ix_onboarding_states_created_by_user_id", "onboarding_states", ["created_by_user_id"])


def downgrade():
    op.drop_index("ix_onboarding_states_created_by_user_id", table_name="onboarding_states")
    op.drop_index("ix_onboarding_states_first_website_id", table_name="onboarding_states")
    op.drop_index("ix_onboarding_states_tenant_id", table_name="onboarding_states")
    op.drop_table("onboarding_states")
