"""create incident recoveries table

Revision ID: ffc2d3e4f5f6
Revises: ffb1c2d3e4f5
Create Date: 2026-01-20 16:15:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ffc2d3e4f5f6"
down_revision: Union[str, None] = "ffb1c2d3e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    json_type = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")
    op.create_table(
        "incident_recoveries",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
        ),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("website_id", sa.Integer(), nullable=True),
        sa.Column("environment_id", sa.Integer(), nullable=True),
        sa.Column(
            "incident_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            nullable=False,
        ),
        sa.Column("measured_at", sa.DateTime(), nullable=False),
        sa.Column("window_start", sa.DateTime(), nullable=False),
        sa.Column("window_end", sa.DateTime(), nullable=False),
        sa.Column("post_conversion_rate", sa.Float(), nullable=False),
        sa.Column("change_in_errors", sa.Float(), nullable=True),
        sa.Column("change_in_threats", sa.Float(), nullable=True),
        sa.Column("recovery_ratio", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence_json", json_type, nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["environment_id"], ["website_environments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_incident_recoveries_tenant_incident",
        "incident_recoveries",
        ["tenant_id", "incident_id"],
    )
    op.create_index(
        "ix_incident_recoveries_tenant_measured_at",
        "incident_recoveries",
        ["tenant_id", "measured_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_incident_recoveries_tenant_measured_at", table_name="incident_recoveries")
    op.drop_index("ix_incident_recoveries_tenant_incident", table_name="incident_recoveries")
    op.drop_table("incident_recoveries")
