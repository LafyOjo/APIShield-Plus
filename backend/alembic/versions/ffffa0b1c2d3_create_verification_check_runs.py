"""create verification check runs

Revision ID: ffffa0b1c2d3
Revises: ffff9f0a1b2c
Create Date: 2026-01-25 15:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "ffffa0b1c2d3"
down_revision = "ffff9f0a1b2c"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "verification_check_runs",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("website_id", sa.Integer(), nullable=True),
        sa.Column("environment_id", sa.Integer(), nullable=True),
        sa.Column("incident_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("checks_json", sa.JSON(), nullable=False),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["environment_id"], ["website_environments.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_verification_runs_tenant_incident", "verification_check_runs", ["tenant_id", "incident_id"])
    op.create_index("ix_verification_runs_tenant_created", "verification_check_runs", ["tenant_id", "created_at"])
    op.create_index("ix_verification_check_runs_tenant_id", "verification_check_runs", ["tenant_id"])
    op.create_index("ix_verification_check_runs_incident_id", "verification_check_runs", ["incident_id"])
    op.create_index("ix_verification_check_runs_website_id", "verification_check_runs", ["website_id"])
    op.create_index("ix_verification_check_runs_environment_id", "verification_check_runs", ["environment_id"])


def downgrade():
    op.drop_index("ix_verification_check_runs_environment_id", table_name="verification_check_runs")
    op.drop_index("ix_verification_check_runs_website_id", table_name="verification_check_runs")
    op.drop_index("ix_verification_check_runs_incident_id", table_name="verification_check_runs")
    op.drop_index("ix_verification_check_runs_tenant_id", table_name="verification_check_runs")
    op.drop_index("ix_verification_runs_tenant_created", table_name="verification_check_runs")
    op.drop_index("ix_verification_runs_tenant_incident", table_name="verification_check_runs")
    op.drop_table("verification_check_runs")
