"""create prescription bundles table

Revision ID: ff9c0d1e2f3a
Revises: ff8c9d0e1f2a
Create Date: 2026-01-20 11:12:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ff9c0d1e2f3a"
down_revision: Union[str, None] = "ff8c9d0e1f2a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    json_type = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")
    op.create_table(
        "prescription_bundles",
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
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("items_json", json_type, nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("notes", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["environment_id"], ["website_environments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_prescription_bundles_tenant_incident",
        "prescription_bundles",
        ["tenant_id", "incident_id"],
    )
    op.create_index(
        "ix_prescription_bundles_tenant_created_at",
        "prescription_bundles",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_prescription_bundles_tenant_created_at", table_name="prescription_bundles")
    op.drop_index("ix_prescription_bundles_tenant_incident", table_name="prescription_bundles")
    op.drop_table("prescription_bundles")
