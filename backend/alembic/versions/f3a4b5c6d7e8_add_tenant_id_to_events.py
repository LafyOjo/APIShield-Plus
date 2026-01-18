"""add tenant_id to events

Revision ID: f3a4b5c6d7e8
Revises: f2e3d4c5b6a7
Create Date: 2026-01-15 12:00:00.000000
"""

from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, None] = "f2e3d4c5b6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_TENANT_NAME = "Default Workspace"
DEFAULT_TENANT_SLUG = "default"


def _get_or_create_default_tenant_id(conn) -> int:
    row = conn.execute(
        sa.text("SELECT id FROM tenants WHERE slug = :slug"),
        {"slug": DEFAULT_TENANT_SLUG},
    ).fetchone()
    if row:
        return int(row[0])

    count = conn.execute(sa.text("SELECT COUNT(*) FROM tenants")).scalar()
    if count == 0:
        now = datetime.now(timezone.utc)
        conn.execute(
            sa.text(
                "INSERT INTO tenants (name, slug, created_at, updated_at) "
                "VALUES (:name, :slug, :created_at, :updated_at)"
            ),
            {
                "name": DEFAULT_TENANT_NAME,
                "slug": DEFAULT_TENANT_SLUG,
                "created_at": now,
                "updated_at": now,
            },
        )
        row = conn.execute(
            sa.text("SELECT id FROM tenants WHERE slug = :slug"),
            {"slug": DEFAULT_TENANT_SLUG},
        ).fetchone()
        if row:
            return int(row[0])

    raise RuntimeError("Default tenant not found; run backfill before migration.")


def upgrade() -> None:
    with op.batch_alter_table("events") as batch_op:
        batch_op.add_column(sa.Column("tenant_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_events_tenant_id",
            "tenants",
            ["tenant_id"],
            ["id"],
        )
        batch_op.create_index("ix_events_tenant_id", ["tenant_id"], unique=False)

    conn = op.get_bind()
    tenant_id = _get_or_create_default_tenant_id(conn)
    conn.execute(
        sa.text("UPDATE events SET tenant_id = :tenant_id WHERE tenant_id IS NULL"),
        {"tenant_id": tenant_id},
    )

    with op.batch_alter_table("events") as batch_op:
        batch_op.alter_column("tenant_id", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("events") as batch_op:
        batch_op.drop_index("ix_events_tenant_id")
        batch_op.drop_constraint("fk_events_tenant_id", type_="foreignkey")
        batch_op.drop_column("tenant_id")
