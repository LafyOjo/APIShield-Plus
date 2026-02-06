"""create reseller account tables

Revision ID: fffffb1c2d3e
Revises: fffffa1b2c3d
Create Date: 2026-02-02 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "fffffb1c2d3e"
down_revision = "fffffa1b2c3d"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "reseller_accounts",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("partner_id", sa.Integer(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("billing_mode", sa.String(), nullable=False, server_default="customer_pays_stripe"),
        sa.Column("allowed_plans", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["partner_id"], ["affiliate_partners.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("partner_id", name="uq_reseller_accounts_partner"),
    )

    op.create_table(
        "managed_tenants",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("reseller_partner_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["reseller_partner_id"], ["affiliate_partners.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", name="uq_managed_tenants_tenant"),
    )
    op.create_index("ix_managed_tenants_partner", "managed_tenants", ["reseller_partner_id"])
    op.create_index("ix_managed_tenants_status", "managed_tenants", ["status"])

    op.alter_column("reseller_accounts", "is_enabled", server_default=None)
    op.alter_column("reseller_accounts", "billing_mode", server_default=None)
    op.alter_column("managed_tenants", "status", server_default=None)


def downgrade():
    op.drop_index("ix_managed_tenants_status", table_name="managed_tenants")
    op.drop_index("ix_managed_tenants_partner", table_name="managed_tenants")
    op.drop_table("managed_tenants")
    op.drop_table("reseller_accounts")
