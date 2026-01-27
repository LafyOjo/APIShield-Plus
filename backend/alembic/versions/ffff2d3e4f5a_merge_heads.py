"""merge heads fffe6f7a8b9c and ffff1c2d3e4f

Revision ID: ffff2d3e4f5a
Revises: fffe6f7a8b9c, ffff1c2d3e4f
Create Date: 2026-01-24 00:05:00.000000
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ffff2d3e4f5a"
down_revision: Union[str, Sequence[str], None] = ("fffe6f7a8b9c", "ffff1c2d3e4f")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
