"""add tenant data region fields

Revision ID: ffff3e4f5a6b
Revises: ffff2d3e4f5a
Create Date: 2026-01-24 00:10:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ffff3e4f5a6b"
down_revision: Union[str, None] = "ffff2d3e4f5a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("tenants") as batch_op:
        batch_op.add_column(
            sa.Column("data_region", sa.String(), nullable=False, server_default="us")
        )
        batch_op.add_column(
            sa.Column("created_region", sa.String(), nullable=False, server_default="us")
        )
        batch_op.add_column(sa.Column("allowed_regions", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("tenants") as batch_op:
        batch_op.drop_column("allowed_regions")
        batch_op.drop_column("created_region")
        batch_op.drop_column("data_region")
