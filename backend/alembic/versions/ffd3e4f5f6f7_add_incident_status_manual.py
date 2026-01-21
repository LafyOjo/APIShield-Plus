"""add incident status manual flag

Revision ID: ffd3e4f5f6f7
Revises: ffc2d3e4f5f6
Create Date: 2026-01-21 08:35:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ffd3e4f5f6f7"
down_revision: Union[str, None] = "ffc2d3e4f5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "incidents",
        sa.Column(
            "status_manual",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column("incidents", "status_manual", server_default=None)


def downgrade() -> None:
    op.drop_column("incidents", "status_manual")
