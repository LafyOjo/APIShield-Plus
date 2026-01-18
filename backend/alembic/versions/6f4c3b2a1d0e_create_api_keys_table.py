"""create api_keys table

Revision ID: 6f4c3b2a1d0e
Revises: 9d3e2f1c0b8a
Create Date: 2026-01-12 22:10:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6f4c3b2a1d0e"
down_revision: Union[str, None] = "9d3e2f1c0b8a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("website_id", sa.Integer(), sa.ForeignKey("websites.id"), nullable=False),
        sa.Column(
            "environment_id",
            sa.Integer(),
            sa.ForeignKey("website_environments.id"),
            nullable=False,
        ),
        sa.Column("public_key", sa.String(), nullable=False),
        sa.Column("secret_hash", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index(op.f("ix_api_keys_id"), "api_keys", ["id"], unique=False)
    op.create_index(
        op.f("ix_api_keys_public_key"),
        "api_keys",
        ["public_key"],
        unique=True,
    )
    op.create_index(
        "ix_api_keys_tenant_environment",
        "api_keys",
        ["tenant_id", "environment_id"],
        unique=False,
    )
    op.create_index(
        "ix_api_keys_tenant_created_at",
        "api_keys",
        ["tenant_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_api_keys_tenant_created_at", table_name="api_keys")
    op.drop_index("ix_api_keys_tenant_environment", table_name="api_keys")
    op.drop_index(op.f("ix_api_keys_public_key"), table_name="api_keys")
    op.drop_index(op.f("ix_api_keys_id"), table_name="api_keys")
    op.drop_table("api_keys")
