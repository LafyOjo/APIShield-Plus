"""create security_events table

Revision ID: ff6a7b8c9d0e
Revises: ff5f6a7b8c9d
Create Date: 2026-01-19 12:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ff6a7b8c9d0e"
down_revision: Union[str, None] = "ff5f6a7b8c9d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    json_type = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")
    op.create_table(
        "security_events",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
        ),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("website_id", sa.Integer(), nullable=True),
        sa.Column("environment_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("event_ts", sa.DateTime(), nullable=True),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("request_path", sa.String(), nullable=True),
        sa.Column("method", sa.String(), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("user_identifier", sa.String(), nullable=True),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("client_ip", sa.String(), nullable=True),
        sa.Column("user_agent", sa.String(), nullable=True),
        sa.Column("ip_hash", sa.String(), nullable=True),
        sa.Column("country_code", sa.String(), nullable=True),
        sa.Column("region", sa.String(), nullable=True),
        sa.Column("city", sa.String(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("asn_number", sa.Integer(), nullable=True),
        sa.Column("asn_org", sa.String(), nullable=True),
        sa.Column("is_datacenter", sa.Boolean(), nullable=True),
        sa.Column("meta", json_type, nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["environment_id"], ["website_environments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_security_events_tenant_created_at",
        "security_events",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_security_events_tenant_category_created_at",
        "security_events",
        ["tenant_id", "category", "created_at"],
    )
    op.create_index(
        "ix_security_events_tenant_event_type_created_at",
        "security_events",
        ["tenant_id", "event_type", "created_at"],
    )
    op.create_index(
        "ix_security_events_tenant_ip_hash_created_at",
        "security_events",
        ["tenant_id", "ip_hash", "created_at"],
    )
    op.create_index(
        "ix_security_events_tenant_website_created_at",
        "security_events",
        ["tenant_id", "website_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_security_events_tenant_website_created_at", table_name="security_events")
    op.drop_index("ix_security_events_tenant_ip_hash_created_at", table_name="security_events")
    op.drop_index("ix_security_events_tenant_event_type_created_at", table_name="security_events")
    op.drop_index("ix_security_events_tenant_category_created_at", table_name="security_events")
    op.drop_index("ix_security_events_tenant_created_at", table_name="security_events")
    op.drop_table("security_events")
