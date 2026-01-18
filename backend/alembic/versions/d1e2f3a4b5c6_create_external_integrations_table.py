"""create external integrations table

Revision ID: d1e2f3a4b5c6
Revises: c7d8e9f0a1b2
Create Date: 2026-01-15 04:20:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "external_integrations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("config_encrypted", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'active'")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(op.f("ix_external_integrations_id"), "external_integrations", ["id"], unique=False)
    op.create_index(
        op.f("ix_external_integrations_tenant_id"),
        "external_integrations",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_external_integrations_type"),
        "external_integrations",
        ["type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_external_integrations_type"), table_name="external_integrations")
    op.drop_index(op.f("ix_external_integrations_tenant_id"), table_name="external_integrations")
    op.drop_index(op.f("ix_external_integrations_id"), table_name="external_integrations")
    op.drop_table("external_integrations")
