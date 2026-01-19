"""create geo_event_aggs table

Revision ID: ff5f6a7b8c9d
Revises: ff4e5f6a7b8c
Create Date: 2026-01-18 23:10:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ff5f6a7b8c9d"
down_revision: Union[str, None] = "ff4e5f6a7b8c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "geo_event_aggs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("website_id", sa.Integer(), nullable=True),
        sa.Column("environment_id", sa.Integer(), nullable=True),
        sa.Column("bucket_start", sa.DateTime(), nullable=False),
        sa.Column("event_category", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=True),
        sa.Column("country_code", sa.String(), nullable=True),
        sa.Column("region", sa.String(), nullable=True),
        sa.Column("city", sa.String(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("asn_number", sa.Integer(), nullable=True),
        sa.Column("asn_org", sa.String(), nullable=True),
        sa.Column("is_datacenter", sa.Boolean(), nullable=True),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["environment_id"], ["website_environments.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "tenant_id",
            "website_id",
            "environment_id",
            "bucket_start",
            "event_category",
            "severity",
            "country_code",
            "region",
            "city",
            "latitude",
            "longitude",
            "asn_number",
            "asn_org",
            "is_datacenter",
            name="uq_geo_event_aggs_bucket_dims",
        ),
    )
    op.create_index("ix_geo_event_aggs_tenant_bucket", "geo_event_aggs", ["tenant_id", "bucket_start"])
    op.create_index(
        "ix_geo_event_aggs_tenant_website_bucket",
        "geo_event_aggs",
        ["tenant_id", "website_id", "bucket_start"],
    )
    op.create_index(
        "ix_geo_event_aggs_tenant_bucket_country",
        "geo_event_aggs",
        ["tenant_id", "bucket_start", "country_code"],
    )
    op.create_index(
        "ix_geo_event_aggs_tenant_bucket_latlon",
        "geo_event_aggs",
        ["tenant_id", "bucket_start", "latitude", "longitude"],
    )


def downgrade() -> None:
    op.drop_index("ix_geo_event_aggs_tenant_bucket_latlon", table_name="geo_event_aggs")
    op.drop_index("ix_geo_event_aggs_tenant_bucket_country", table_name="geo_event_aggs")
    op.drop_index("ix_geo_event_aggs_tenant_website_bucket", table_name="geo_event_aggs")
    op.drop_index("ix_geo_event_aggs_tenant_bucket", table_name="geo_event_aggs")
    op.drop_table("geo_event_aggs")
