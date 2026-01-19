"""create ip_enrichments table

Revision ID: ff4e5f6a7b8c
Revises: ff3d4e5f6a7b
Create Date: 2026-01-18 22:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ff4e5f6a7b8c"
down_revision: Union[str, None] = "ff3d4e5f6a7b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ip_enrichments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("ip_hash", sa.String(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("country_code", sa.String(), nullable=True),
        sa.Column("region", sa.String(), nullable=True),
        sa.Column("city", sa.String(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("asn_number", sa.Integer(), nullable=True),
        sa.Column("asn_org", sa.String(), nullable=True),
        sa.Column("is_datacenter", sa.Boolean(), nullable=True),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("last_lookup_at", sa.DateTime(), nullable=True),
        sa.Column("lookup_status", sa.String(), nullable=False),
        sa.Column("failure_reason", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", "ip_hash", name="uq_ip_enrichments_tenant_ip_hash"),
    )
    op.create_index("ix_ip_enrichments_tenant_id", "ip_enrichments", ["tenant_id"])
    op.create_index("ix_ip_enrichments_ip_hash", "ip_enrichments", ["ip_hash"])
    op.create_index(
        "ix_ip_enrichments_tenant_last_seen",
        "ip_enrichments",
        ["tenant_id", "last_seen_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ip_enrichments_tenant_last_seen", table_name="ip_enrichments")
    op.drop_index("ix_ip_enrichments_ip_hash", table_name="ip_enrichments")
    op.drop_index("ix_ip_enrichments_tenant_id", table_name="ip_enrichments")
    op.drop_table("ip_enrichments")
