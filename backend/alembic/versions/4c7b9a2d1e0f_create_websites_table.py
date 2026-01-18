"""create websites table

Revision ID: 4c7b9a2d1e0f
Revises: 1a2b3c4d5e6f
Create Date: 2026-01-12 21:10:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4c7b9a2d1e0f"
down_revision: Union[str, None] = "1a2b3c4d5e6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "websites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("domain", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("tenant_id", "domain", name="uq_websites_tenant_domain"),
    )
    op.create_index(op.f("ix_websites_id"), "websites", ["id"], unique=False)
    op.create_index(
        "ix_websites_tenant_created_at",
        "websites",
        ["tenant_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_websites_tenant_created_at", table_name="websites")
    op.drop_index(op.f("ix_websites_id"), table_name="websites")
    op.drop_table("websites")
