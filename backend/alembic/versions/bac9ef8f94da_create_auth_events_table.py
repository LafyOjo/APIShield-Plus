"""create auth_events table

Revision ID: bac9ef8f94da
Revises: fffff
Create Date: 2025-08-09 08:47:23.879942

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bac9ef8f94da'
down_revision: Union[str, None] = 'fffff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auth_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user", sa.String(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column(
            "success", sa.Boolean(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(op.f("ix_auth_events_id"), "auth_events", ["id"], unique=False)
    op.create_index(
        op.f("ix_auth_events_created_at"),
        "auth_events",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_auth_events_created_at"), table_name="auth_events")
    op.drop_index(op.f("ix_auth_events_id"), table_name="auth_events")
    op.drop_table("auth_events")
