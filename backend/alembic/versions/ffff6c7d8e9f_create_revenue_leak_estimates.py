"""create revenue leak estimates table

Revision ID: ffff6c7d8e9f
Revises: ffff5b6c7d8e
Create Date: 2026-01-24 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ffff6c7d8e9f"
down_revision: Union[str, None] = "ffff5b6c7d8e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "revenue_leak_estimates",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("website_id", sa.Integer(), nullable=False),
        sa.Column("environment_id", sa.Integer(), nullable=False),
        sa.Column("bucket_start", sa.DateTime(), nullable=False),
        sa.Column("path", sa.String(), nullable=True),
        sa.Column("baseline_conversion_rate", sa.Float(), nullable=True),
        sa.Column("observed_conversion_rate", sa.Float(), nullable=False),
        sa.Column("sessions_in_bucket", sa.Integer(), nullable=False),
        sa.Column("expected_conversions", sa.Float(), nullable=False),
        sa.Column("observed_conversions", sa.Integer(), nullable=False),
        sa.Column("lost_conversions", sa.Float(), nullable=False),
        sa.Column("revenue_per_conversion", sa.Float(), nullable=True),
        sa.Column("estimated_lost_revenue", sa.Float(), nullable=True),
        sa.Column("linked_trust_score", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("explanation_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["environment_id"], ["website_environments.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "tenant_id",
            "website_id",
            "environment_id",
            "path",
            "bucket_start",
            name="uq_revenue_leak_tenant_path_bucket",
        ),
    )
    op.create_index(
        "ix_revenue_leak_tenant_site_bucket",
        "revenue_leak_estimates",
        ["tenant_id", "website_id", "bucket_start"],
    )
    op.create_index(
        "ix_revenue_leak_tenant_site_path_bucket",
        "revenue_leak_estimates",
        ["tenant_id", "website_id", "path", "bucket_start"],
    )


def downgrade() -> None:
    op.drop_index("ix_revenue_leak_tenant_site_path_bucket", table_name="revenue_leak_estimates")
    op.drop_index("ix_revenue_leak_tenant_site_bucket", table_name="revenue_leak_estimates")
    op.drop_table("revenue_leak_estimates")
