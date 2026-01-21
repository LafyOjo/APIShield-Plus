"""create prescription items table

Revision ID: ffb1c2d3e4f5
Revises: ffa0b1c2d3e4
Create Date: 2026-01-20 12:05:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ffb1c2d3e4f5"
down_revision: Union[str, None] = "ffa0b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    json_type = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")
    op.create_table(
        "prescription_items",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
        ),
        sa.Column(
            "bundle_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("website_id", sa.Integer(), nullable=True),
        sa.Column("environment_id", sa.Integer(), nullable=True),
        sa.Column(
            "incident_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            nullable=False,
        ),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("priority", sa.String(), nullable=False),
        sa.Column("effort", sa.String(), nullable=False),
        sa.Column("expected_effect", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("applied_at", sa.DateTime(), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(), nullable=True),
        sa.Column("snoozed_until", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("applied_by_user_id", sa.Integer(), nullable=True),
        sa.Column("evidence_json", json_type, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["bundle_id"], ["prescription_bundles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["environment_id"], ["website_environments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["applied_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_prescription_items_tenant_incident",
        "prescription_items",
        ["tenant_id", "incident_id"],
    )
    op.create_index(
        "ix_prescription_items_tenant_status",
        "prescription_items",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_prescription_items_bundle",
        "prescription_items",
        ["bundle_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_prescription_items_bundle", table_name="prescription_items")
    op.drop_index("ix_prescription_items_tenant_status", table_name="prescription_items")
    op.drop_index("ix_prescription_items_tenant_incident", table_name="prescription_items")
    op.drop_table("prescription_items")
