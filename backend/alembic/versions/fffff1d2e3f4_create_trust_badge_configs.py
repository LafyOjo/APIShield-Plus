"""create trust badge configs

Revision ID: fffff1d2e3f4
Revises: fffff0c1d2e3
Create Date: 2026-01-31 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "fffff1d2e3f4"
down_revision = "fffff0c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trust_badge_configs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("website_id", sa.Integer(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("style", sa.String(), nullable=False, server_default="light"),
        sa.Column("show_score", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("show_branding", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("clickthrough_url", sa.String(), nullable=True),
        sa.Column("badge_key_enc", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "website_id", name="uq_trust_badge_tenant_website"),
    )
    op.create_index("ix_trust_badge_website", "trust_badge_configs", ["website_id"], unique=False)
    op.create_index("ix_trust_badge_tenant", "trust_badge_configs", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_trust_badge_tenant", table_name="trust_badge_configs")
    op.drop_index("ix_trust_badge_website", table_name="trust_badge_configs")
    op.drop_table("trust_badge_configs")
