"""create behaviour_events table

Revision ID: fe1a2b3c4d5e
Revises: fd2e3f4a5b6c
Create Date: 2026-01-18 14:10:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "fe1a2b3c4d5e"
down_revision: Union[str, None] = "fd2e3f4a5b6c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    json_type = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")
    op.create_table(
        "behaviour_events",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
        ),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("website_id", sa.Integer(), nullable=False),
        sa.Column("environment_id", sa.Integer(), nullable=False),
        sa.Column("ingested_at", sa.DateTime(), nullable=False),
        sa.Column("event_ts", sa.DateTime(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("path", sa.String(), nullable=True),
        sa.Column("referrer", sa.Text(), nullable=True),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("visitor_id", sa.String(), nullable=True),
        sa.Column("ip_hash", sa.String(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("meta", json_type, nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["environment_id"], ["website_environments.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_behaviour_events_tenant_ingested_at",
        "behaviour_events",
        ["tenant_id", "ingested_at"],
    )
    op.create_index(
        "ix_behaviour_events_tenant_website_ingested_at",
        "behaviour_events",
        ["tenant_id", "website_id", "ingested_at"],
    )
    op.create_index(
        "ix_behaviour_events_tenant_session_ingested_at",
        "behaviour_events",
        ["tenant_id", "session_id", "ingested_at"],
    )
    op.create_index(
        "ix_behaviour_events_tenant_path_ingested_at",
        "behaviour_events",
        ["tenant_id", "path", "ingested_at"],
    )
    op.create_index(
        "ix_behaviour_events_tenant_ip_hash_ingested_at",
        "behaviour_events",
        ["tenant_id", "ip_hash", "ingested_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_behaviour_events_tenant_ip_hash_ingested_at", table_name="behaviour_events")
    op.drop_index("ix_behaviour_events_tenant_path_ingested_at", table_name="behaviour_events")
    op.drop_index("ix_behaviour_events_tenant_session_ingested_at", table_name="behaviour_events")
    op.drop_index("ix_behaviour_events_tenant_website_ingested_at", table_name="behaviour_events")
    op.drop_index("ix_behaviour_events_tenant_ingested_at", table_name="behaviour_events")
    op.drop_table("behaviour_events")
