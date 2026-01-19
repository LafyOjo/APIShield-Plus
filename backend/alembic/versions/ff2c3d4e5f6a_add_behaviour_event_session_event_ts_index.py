"""add behaviour_events session event_ts index

Revision ID: ff2c3d4e5f6a
Revises: ff1b2c3d4e5f
Create Date: 2026-01-18 17:40:00.000000
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ff2c3d4e5f6a"
down_revision: Union[str, None] = "ff1b2c3d4e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_behaviour_events_tenant_session_event_ts",
        "behaviour_events",
        ["tenant_id", "session_id", "event_ts"],
    )


def downgrade() -> None:
    op.drop_index("ix_behaviour_events_tenant_session_event_ts", table_name="behaviour_events")
