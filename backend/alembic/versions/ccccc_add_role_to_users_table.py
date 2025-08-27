"""add role column to users table

Revision ID: ccccc
Revises: bb1f5f0e5d4a
Create Date: 2025-06-13 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'ccccc'
down_revision: Union[str, None] = 'bb1f5f0e5d4a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("role", sa.String(), nullable=False, server_default="user"),
    )


def downgrade() -> None:
    op.drop_column('users', 'role')
