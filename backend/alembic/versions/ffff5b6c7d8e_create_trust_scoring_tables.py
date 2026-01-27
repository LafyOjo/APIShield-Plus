"""create trust scoring tables

Revision ID: ffff5b6c7d8e
Revises: ffff4a5b6c7d
Create Date: 2026-01-24 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ffff5b6c7d8e"
down_revision: Union[str, None] = "ffff4a5b6c7d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trust_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("website_id", sa.Integer(), nullable=False),
        sa.Column("environment_id", sa.Integer(), nullable=False),
        sa.Column("bucket_start", sa.DateTime(), nullable=False),
        sa.Column("path", sa.String(), nullable=True),
        sa.Column("trust_score", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("factor_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["environment_id"], ["website_environments.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_trust_snapshots_tenant_website_bucket",
        "trust_snapshots",
        ["tenant_id", "website_id", "bucket_start"],
    )
    op.create_index(
        "ix_trust_snapshots_tenant_website_path_bucket",
        "trust_snapshots",
        ["tenant_id", "website_id", "path", "bucket_start"],
    )

    op.create_table(
        "trust_factor_aggs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("website_id", sa.Integer(), nullable=False),
        sa.Column("environment_id", sa.Integer(), nullable=False),
        sa.Column("bucket_start", sa.DateTime(), nullable=False),
        sa.Column("path", sa.String(), nullable=True),
        sa.Column("factor_type", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evidence_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["environment_id"], ["website_environments.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_trust_factor_aggs_tenant_website_bucket",
        "trust_factor_aggs",
        ["tenant_id", "website_id", "bucket_start"],
    )
    op.create_index(
        "ix_trust_factor_aggs_tenant_website_path_bucket",
        "trust_factor_aggs",
        ["tenant_id", "website_id", "path", "bucket_start"],
    )
    op.create_index(
        "ix_trust_factor_aggs_tenant_factor",
        "trust_factor_aggs",
        ["tenant_id", "factor_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_trust_factor_aggs_tenant_factor", table_name="trust_factor_aggs")
    op.drop_index("ix_trust_factor_aggs_tenant_website_path_bucket", table_name="trust_factor_aggs")
    op.drop_index("ix_trust_factor_aggs_tenant_website_bucket", table_name="trust_factor_aggs")
    op.drop_table("trust_factor_aggs")

    op.drop_index("ix_trust_snapshots_tenant_website_path_bucket", table_name="trust_snapshots")
    op.drop_index("ix_trust_snapshots_tenant_website_bucket", table_name="trust_snapshots")
    op.drop_table("trust_snapshots")
