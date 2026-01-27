"""create tenant sso config table

Revision ID: fff9d0e1f2a3
Revises: fff8c9d0e1f2
Create Date: 2026-01-23 12:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "fff9d0e1f2a3"
down_revision: Union[str, None] = "fff8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenant_sso_configs",
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("issuer_url", sa.String(), nullable=False),
        sa.Column("client_id", sa.String(), nullable=False),
        sa.Column("client_secret_enc", sa.Text(), nullable=False),
        sa.Column("redirect_uri", sa.String(), nullable=False),
        sa.Column("scopes", sa.String(), nullable=False),
        sa.Column("allowed_email_domains", sa.JSON(), nullable=True),
        sa.Column("sso_required", sa.Boolean(), nullable=False),
        sa.Column("auto_provision", sa.Boolean(), nullable=False),
        sa.Column("last_tested_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("tenant_sso_configs")
