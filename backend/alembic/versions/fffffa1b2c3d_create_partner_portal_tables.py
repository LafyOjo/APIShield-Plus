"""create partner portal tables

Revision ID: fffffa1b2c3d
Revises: fffff9b0c2d3
Create Date: 2026-02-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "fffffa1b2c3d"
down_revision = "fffff9b0c2d3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "partner_users",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("partner_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False, server_default="viewer"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["partner_id"], ["affiliate_partners.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("partner_id", "user_id", name="uq_partner_users_partner_user"),
    )
    op.create_index("ix_partner_users_partner", "partner_users", ["partner_id"])
    op.create_index("ix_partner_users_user", "partner_users", ["user_id"])

    op.create_table(
        "partner_leads",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("partner_id", sa.Integer(), nullable=False),
        sa.Column("lead_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="new"),
        sa.Column("source_meta_json", sa.JSON(), nullable=True),
        sa.Column("associated_tenant_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["partner_id"], ["affiliate_partners.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["associated_tenant_id"], ["tenants.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("lead_id", name="uq_partner_leads_lead_id"),
    )
    op.create_index("ix_partner_leads_partner", "partner_leads", ["partner_id"])
    op.create_index("ix_partner_leads_status", "partner_leads", ["status"])

    op.alter_column("partner_users", "role", server_default=None)
    op.alter_column("partner_leads", "status", server_default=None)


def downgrade():
    op.drop_index("ix_partner_leads_status", table_name="partner_leads")
    op.drop_index("ix_partner_leads_partner", table_name="partner_leads")
    op.drop_table("partner_leads")
    op.drop_index("ix_partner_users_user", table_name="partner_users")
    op.drop_index("ix_partner_users_partner", table_name="partner_users")
    op.drop_table("partner_users")
