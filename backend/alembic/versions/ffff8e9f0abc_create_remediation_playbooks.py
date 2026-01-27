"""create remediation playbooks

Revision ID: ffff8e9f0abc
Revises: ffff7d8e9fab
Create Date: 2026-01-25 12:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "ffff8e9f0abc"
down_revision = "ffff7d8e9fab"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "remediation_playbooks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("website_id", sa.Integer(), nullable=True),
        sa.Column("environment_id", sa.Integer(), nullable=True),
        sa.Column("incident_id", sa.Integer(), nullable=False),
        sa.Column("stack_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("sections_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["environment_id"], ["website_environments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_playbooks_tenant_incident",
        "remediation_playbooks",
        ["tenant_id", "incident_id"],
        unique=False,
    )
    op.create_index(
        "ix_playbooks_tenant_created",
        "remediation_playbooks",
        ["tenant_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_playbooks_tenant_created", table_name="remediation_playbooks")
    op.drop_index("ix_playbooks_tenant_incident", table_name="remediation_playbooks")
    op.drop_table("remediation_playbooks")
