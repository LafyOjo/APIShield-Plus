"""create behaviour_sessions table

Revision ID: ff1b2c3d4e5f
Revises: ff0a1b2c3d4e
Create Date: 2026-01-18 17:10:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ff1b2c3d4e5f"
down_revision: Union[str, None] = "ff0a1b2c3d4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "behaviour_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("website_id", sa.Integer(), nullable=False),
        sa.Column("environment_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("page_views", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ip_hash", sa.String(), nullable=True),
        sa.Column("entry_path", sa.String(), nullable=True),
        sa.Column("exit_path", sa.String(), nullable=True),
        sa.Column("country_code", sa.String(), nullable=True),
        sa.Column("region", sa.String(), nullable=True),
        sa.Column("city", sa.String(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("asn", sa.String(), nullable=True),
        sa.Column("is_datacenter", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["environment_id"], ["website_environments.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "tenant_id",
            "environment_id",
            "session_id",
            name="uq_behaviour_sessions_tenant_env_session_id",
        ),
    )
    op.create_index(
        "ix_behaviour_sessions_tenant_website_started_at",
        "behaviour_sessions",
        ["tenant_id", "website_id", "started_at"],
    )
    op.create_index(
        "ix_behaviour_sessions_tenant_session_id",
        "behaviour_sessions",
        ["tenant_id", "session_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_behaviour_sessions_tenant_session_id", table_name="behaviour_sessions")
    op.drop_index("ix_behaviour_sessions_tenant_website_started_at", table_name="behaviour_sessions")
    op.drop_table("behaviour_sessions")
