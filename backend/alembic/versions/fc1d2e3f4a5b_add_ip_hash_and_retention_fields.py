"""add ip hash to alerts and retention defaults to tenant settings

Revision ID: fc1d2e3f4a5b
Revises: fb2c3d4e5f6a
Create Date: 2026-01-18 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "fc1d2e3f4a5b"
down_revision: Union[str, None] = "fb2c3d4e5f6a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("tenant_settings") as batch_op:
        batch_op.add_column(
            sa.Column(
                "event_retention_days",
                sa.Integer(),
                nullable=False,
                server_default="30",
            )
        )
        batch_op.add_column(
            sa.Column(
                "ip_raw_retention_days",
                sa.Integer(),
                nullable=False,
                server_default="7",
            )
        )
        batch_op.alter_column("retention_days", server_default="30")

    op.execute(
        "UPDATE tenant_settings SET event_retention_days = retention_days "
        "WHERE event_retention_days IS NULL"
    )
    op.execute(
        "UPDATE tenant_settings SET ip_raw_retention_days = 7 "
        "WHERE ip_raw_retention_days IS NULL"
    )

    with op.batch_alter_table("alerts") as batch_op:
        batch_op.add_column(sa.Column("ip_hash", sa.String(), nullable=True))
        batch_op.create_index(
            "ix_alerts_tenant_ip_hash",
            ["tenant_id", "ip_hash"],
        )


def downgrade() -> None:
    with op.batch_alter_table("alerts") as batch_op:
        batch_op.drop_index("ix_alerts_tenant_ip_hash")
        batch_op.drop_column("ip_hash")

    with op.batch_alter_table("tenant_settings") as batch_op:
        batch_op.alter_column("retention_days", server_default="7")
        batch_op.drop_column("ip_raw_retention_days")
        batch_op.drop_column("event_retention_days")
