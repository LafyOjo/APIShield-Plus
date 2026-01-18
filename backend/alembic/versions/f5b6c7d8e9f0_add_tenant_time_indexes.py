"""add tenant time composite indexes

Revision ID: f5b6c7d8e9f0
Revises: f4a5b6c7d8e9
Create Date: 2026-01-16 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f5b6c7d8e9f0"
down_revision: Union[str, None] = "f4a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_events_tenant_time",
        "events",
        ["tenant_id", "timestamp"],
        unique=False,
    )
    op.create_index(
        "ix_audit_tenant_time",
        "audit_logs",
        ["tenant_id", "timestamp"],
        unique=False,
    )

    with op.batch_alter_table("alerts") as batch_op:
        batch_op.add_column(sa.Column("tenant_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_alerts_tenant_id",
            "tenants",
            ["tenant_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_alerts_tenant_time",
            ["tenant_id", "timestamp"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("alerts") as batch_op:
        batch_op.drop_index("ix_alerts_tenant_time")
        batch_op.drop_constraint("fk_alerts_tenant_id", type_="foreignkey")
        batch_op.drop_column("tenant_id")

    op.drop_index("ix_audit_tenant_time", table_name="audit_logs")
    op.drop_index("ix_events_tenant_time", table_name="events")
