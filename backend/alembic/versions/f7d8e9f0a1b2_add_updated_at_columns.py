"""add updated_at columns to invites and domain_verifications

Revision ID: f7d8e9f0a1b2
Revises: f6c7d8e9f0a1
Create Date: 2026-01-16 15:30:00.000000
"""

from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f7d8e9f0a1b2"
down_revision: Union[str, None] = "f6c7d8e9f0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("invites") as batch_op:
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))

    with op.batch_alter_table("domain_verifications") as batch_op:
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))

    now = datetime.now(timezone.utc)
    conn = op.get_bind()
    conn.execute(
        sa.text("UPDATE invites SET updated_at = :now WHERE updated_at IS NULL"),
        {"now": now},
    )
    conn.execute(
        sa.text(
            "UPDATE domain_verifications SET updated_at = :now WHERE updated_at IS NULL"
        ),
        {"now": now},
    )

    with op.batch_alter_table("invites") as batch_op:
        batch_op.alter_column("updated_at", existing_type=sa.DateTime(), nullable=False)

    with op.batch_alter_table("domain_verifications") as batch_op:
        batch_op.alter_column("updated_at", existing_type=sa.DateTime(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("domain_verifications") as batch_op:
        batch_op.drop_column("updated_at")

    with op.batch_alter_table("invites") as batch_op:
        batch_op.drop_column("updated_at")
