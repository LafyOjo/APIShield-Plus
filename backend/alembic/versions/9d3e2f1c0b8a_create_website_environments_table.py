"""create website environments table

Revision ID: 9d3e2f1c0b8a
Revises: 4c7b9a2d1e0f
Create Date: 2026-01-12 21:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9d3e2f1c0b8a"
down_revision: Union[str, None] = "4c7b9a2d1e0f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "website_environments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("website_id", sa.Integer(), sa.ForeignKey("websites.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("base_url", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("website_id", "name", name="uq_website_env_name"),
    )
    op.create_index(
        op.f("ix_website_environments_id"),
        "website_environments",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_website_environments_website_id"),
        "website_environments",
        ["website_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_website_environments_website_id"), table_name="website_environments")
    op.drop_index(op.f("ix_website_environments_id"), table_name="website_environments")
    op.drop_table("website_environments")
