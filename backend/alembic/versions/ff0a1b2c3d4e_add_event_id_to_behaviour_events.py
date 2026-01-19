"""add event_id to behaviour_events for dedupe

Revision ID: ff0a1b2c3d4e
Revises: fe1a2b3c4d5e
Create Date: 2026-01-18 16:45:00.000000
"""
from typing import Sequence, Union
from uuid import uuid4

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ff0a1b2c3d4e"
down_revision: Union[str, None] = "fe1a2b3c4d5e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("behaviour_events") as batch:
        batch.add_column(sa.Column("event_id", sa.String(), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id FROM behaviour_events WHERE event_id IS NULL")).fetchall()
    for row in rows:
        conn.execute(
            sa.text("UPDATE behaviour_events SET event_id = :event_id WHERE id = :id"),
            {"event_id": str(uuid4()), "id": row[0]},
        )

    with op.batch_alter_table("behaviour_events") as batch:
        batch.alter_column("event_id", nullable=False)
        batch.create_unique_constraint(
            "uq_behaviour_events_tenant_env_event_id",
            ["tenant_id", "environment_id", "event_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("behaviour_events") as batch:
        batch.drop_constraint("uq_behaviour_events_tenant_env_event_id", type_="unique")
        batch.drop_column("event_id")
