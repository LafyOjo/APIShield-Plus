"""add website status check constraint

Revision ID: fa1b2c3d4e5f
Revises: f9a0b1c2d3e4
Create Date: 2026-01-16 20:45:00.000000
"""
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "fa1b2c3d4e5f"
down_revision: Union[str, None] = "f9a0b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE websites "
            "SET status = 'active' "
            "WHERE status IS NULL "
            "OR status NOT IN ('active', 'paused', 'deleted')"
        )
    )
    now = datetime.now(timezone.utc)
    conn.execute(
        sa.text(
            "UPDATE websites "
            "SET deleted_at = :now "
            "WHERE status = 'deleted' AND deleted_at IS NULL"
        ),
        {"now": now},
    )
    with op.batch_alter_table("websites") as batch_op:
        batch_op.create_check_constraint(
            "website_status_enum",
            "status IN ('active', 'paused', 'deleted')",
        )


def downgrade() -> None:
    with op.batch_alter_table("websites") as batch_op:
        batch_op.drop_constraint("website_status_enum", type_="check")
