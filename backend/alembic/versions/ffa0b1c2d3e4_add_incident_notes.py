"""add incident notes

Revision ID: ffa0b1c2d3e4
Revises: ff9c0d1e2f3a
Create Date: 2026-01-20 11:22:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ffa0b1c2d3e4"
down_revision: Union[str, None] = "ff9c0d1e2f3a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("incidents", sa.Column("notes", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("incidents", "notes")
