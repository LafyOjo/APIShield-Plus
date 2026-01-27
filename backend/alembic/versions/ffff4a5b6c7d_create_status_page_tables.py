"""create status page tables

Revision ID: ffff4a5b6c7d
Revises: ffff3e4f5a6b
Create Date: 2026-01-24 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ffff4a5b6c7d"
down_revision: Union[str, None] = "ffff3e4f5a6b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


STATUS_COMPONENT_VALUES = "('operational','degraded','outage')"
STATUS_INCIDENT_VALUES = "('investigating','identified','monitoring','resolved')"
STATUS_IMPACT_VALUES = "('minor','major','critical')"


def upgrade() -> None:
    op.create_table(
        "status_components",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("current_status", sa.String(), nullable=False),
        sa.Column("last_updated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("key", name="uq_status_component_key"),
        sa.CheckConstraint(
            f"current_status IN {STATUS_COMPONENT_VALUES}",
            name="status_component_status_enum",
        ),
    )
    op.create_index("ix_status_components_key", "status_components", ["key"], unique=True)

    op.create_table(
        "status_incidents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("impact_level", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("components_affected", sa.JSON(), nullable=False),
        sa.Column("updates", sa.JSON(), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            f"status IN {STATUS_INCIDENT_VALUES}",
            name="status_incident_status_enum",
        ),
        sa.CheckConstraint(
            f"impact_level IN {STATUS_IMPACT_VALUES}",
            name="status_incident_impact_enum",
        ),
    )
    op.create_index("ix_status_incidents_status", "status_incidents", ["status"])
    op.create_index("ix_status_incidents_published", "status_incidents", ["is_published"])


def downgrade() -> None:
    op.drop_index("ix_status_incidents_published", table_name="status_incidents")
    op.drop_index("ix_status_incidents_status", table_name="status_incidents")
    op.drop_table("status_incidents")

    op.drop_index("ix_status_components_key", table_name="status_components")
    op.drop_table("status_components")
