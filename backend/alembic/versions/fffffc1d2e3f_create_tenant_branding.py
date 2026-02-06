"""create tenant branding table

Revision ID: fffffc1d2e3f
Revises: fffffb1c2d3e
Create Date: 2026-02-02 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "fffffc1d2e3f"
down_revision = "fffffb1c2d3e"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tenant_branding",
        sa.Column("tenant_id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("brand_name", sa.String(), nullable=True),
        sa.Column("logo_url", sa.String(), nullable=True),
        sa.Column("primary_color", sa.String(), nullable=True),
        sa.Column("accent_color", sa.String(), nullable=True),
        sa.Column("custom_domain", sa.String(), nullable=True),
        sa.Column("domain_verification_token", sa.String(), nullable=True),
        sa.Column("domain_verified_at", sa.DateTime(), nullable=True),
        sa.Column("badge_branding_mode", sa.String(), nullable=False, server_default="your_brand"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_tenant_branding_custom_domain", "tenant_branding", ["custom_domain"])

    op.alter_column("tenant_branding", "is_enabled", server_default=None)
    op.alter_column("tenant_branding", "badge_branding_mode", server_default=None)


def downgrade():
    op.drop_index("ix_tenant_branding_custom_domain", table_name="tenant_branding")
    op.drop_table("tenant_branding")
