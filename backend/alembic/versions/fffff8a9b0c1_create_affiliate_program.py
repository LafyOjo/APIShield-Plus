"""create affiliate program tables

Revision ID: fffff8a9b0c1
Revises: fffff7a8b9c0
Create Date: 2026-01-30 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "fffff8a9b0c1"
down_revision = "fffff7a8b9c0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "affiliate_partners",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("commission_type", sa.String(), nullable=False, server_default="percent"),
        sa.Column("commission_value", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("payout_method", sa.String(), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("code", name="uq_affiliate_partners_code"),
    )
    op.create_index("ix_affiliate_partners_status", "affiliate_partners", ["status"])

    op.create_table(
        "affiliate_attributions",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("partner_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("first_touch_at", sa.DateTime(), nullable=False),
        sa.Column("last_touch_at", sa.DateTime(), nullable=False),
        sa.Column("source_meta_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["partner_id"], ["affiliate_partners.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", name="uq_affiliate_attributions_tenant"),
    )
    op.create_index("ix_affiliate_attributions_partner", "affiliate_attributions", ["partner_id"])

    op.create_table(
        "affiliate_commission_ledger",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("partner_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("stripe_subscription_id", sa.String(), nullable=True),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(), nullable=False, server_default="GBP"),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("earned_at", sa.DateTime(), nullable=True),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("void_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["partner_id"], ["affiliate_partners.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "partner_id",
            "tenant_id",
            "stripe_subscription_id",
            name="uq_affiliate_commission_unique",
        ),
    )
    op.create_index("ix_affiliate_commission_partner", "affiliate_commission_ledger", ["partner_id"])
    op.create_index("ix_affiliate_commission_status", "affiliate_commission_ledger", ["status"])

    op.alter_column("affiliate_partners", "status", server_default=None)
    op.alter_column("affiliate_partners", "commission_type", server_default=None)
    op.alter_column("affiliate_partners", "commission_value", server_default=None)
    op.alter_column("affiliate_partners", "payout_method", server_default=None)
    op.alter_column("affiliate_commission_ledger", "currency", server_default=None)
    op.alter_column("affiliate_commission_ledger", "status", server_default=None)


def downgrade():
    op.drop_index("ix_affiliate_commission_status", table_name="affiliate_commission_ledger")
    op.drop_index("ix_affiliate_commission_partner", table_name="affiliate_commission_ledger")
    op.drop_table("affiliate_commission_ledger")
    op.drop_index("ix_affiliate_attributions_partner", table_name="affiliate_attributions")
    op.drop_table("affiliate_attributions")
    op.drop_index("ix_affiliate_partners_status", table_name="affiliate_partners")
    op.drop_table("affiliate_partners")
