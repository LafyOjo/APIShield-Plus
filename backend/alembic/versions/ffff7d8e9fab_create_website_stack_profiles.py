"""create website stack profiles

Revision ID: ffff7d8e9fab
Revises: ffff6c7d8e9f
Create Date: 2026-01-25 11:15:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "ffff7d8e9fab"
down_revision = "ffff6c7d8e9f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "website_stack_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("website_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("stack_type", sa.String(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("detected_signals_json", sa.JSON(), nullable=True),
        sa.Column("manual_override", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_stack_profiles_tenant_website",
        "website_stack_profiles",
        ["tenant_id", "website_id"],
        unique=False,
    )
    op.create_index(
        "ix_stack_profiles_website_id",
        "website_stack_profiles",
        ["website_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_stack_profiles_website_id", table_name="website_stack_profiles")
    op.drop_index("ix_stack_profiles_tenant_website", table_name="website_stack_profiles")
    op.drop_table("website_stack_profiles")
