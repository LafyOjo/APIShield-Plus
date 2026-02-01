"""create referral program tables

Revision ID: fffff7a8b9c0
Revises: fffff6a7b8c9
Create Date: 2026-01-30 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "fffff7a8b9c0"
down_revision = "fffff6a7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "referral_program_config",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("reward_type", sa.String(), nullable=False, server_default="credit_gbp"),
        sa.Column("reward_value", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("eligibility_rules_json", sa.JSON(), nullable=False),
        sa.Column("fraud_limits_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "referral_invites",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("max_uses", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("uses_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("code", name="uq_referral_invites_code"),
    )
    op.create_index(
        "ix_referral_invites_tenant_status",
        "referral_invites",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_referral_invites_expires",
        "referral_invites",
        ["expires_at"],
    )

    op.create_table(
        "referral_redemptions",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("invite_id", sa.Integer(), nullable=False),
        sa.Column("new_tenant_id", sa.Integer(), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("reward_applied_at", sa.DateTime(), nullable=True),
        sa.Column("stripe_coupon_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["invite_id"], ["referral_invites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["new_tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("new_tenant_id", name="uq_referral_redemptions_new_tenant"),
    )
    op.create_index(
        "ix_referral_redemptions_invite",
        "referral_redemptions",
        ["invite_id"],
    )
    op.create_index(
        "ix_referral_redemptions_status",
        "referral_redemptions",
        ["status"],
    )

    op.create_table(
        "credit_ledger",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(), nullable=False, server_default="GBP"),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("applied_to_invoice_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_credit_ledger_tenant_created",
        "credit_ledger",
        ["tenant_id", "created_at"],
    )

    op.alter_column("referral_program_config", "is_enabled", server_default=None)
    op.alter_column("referral_program_config", "reward_type", server_default=None)
    op.alter_column("referral_program_config", "reward_value", server_default=None)
    op.alter_column("referral_invites", "max_uses", server_default=None)
    op.alter_column("referral_invites", "uses_count", server_default=None)
    op.alter_column("referral_invites", "status", server_default=None)
    op.alter_column("referral_redemptions", "status", server_default=None)
    op.alter_column("credit_ledger", "currency", server_default=None)


def downgrade():
    op.drop_index("ix_credit_ledger_tenant_created", table_name="credit_ledger")
    op.drop_table("credit_ledger")
    op.drop_index("ix_referral_redemptions_status", table_name="referral_redemptions")
    op.drop_index("ix_referral_redemptions_invite", table_name="referral_redemptions")
    op.drop_table("referral_redemptions")
    op.drop_index("ix_referral_invites_expires", table_name="referral_invites")
    op.drop_index("ix_referral_invites_tenant_status", table_name="referral_invites")
    op.drop_table("referral_invites")
    op.drop_table("referral_program_config")
