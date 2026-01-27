"""add demo mode fields

Revision ID: ffffd3e4f5g6
Revises: ffffc2d3e4f5
Create Date: 2026-01-25
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "ffffd3e4f5g6"
down_revision = "ffffc2d3e4f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("is_demo_mode", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("tenants", sa.Column("demo_seeded_at", sa.DateTime(), nullable=True))
    op.add_column("tenants", sa.Column("demo_expires_at", sa.DateTime(), nullable=True))

    demo_columns = [
        ("behaviour_events", "is_demo"),
        ("behaviour_sessions", "is_demo"),
        ("security_events", "is_demo"),
        ("geo_event_aggs", "is_demo"),
        ("ip_enrichments", "is_demo"),
        ("incidents", "is_demo"),
        ("trust_snapshots", "is_demo"),
        ("trust_factor_aggs", "is_demo"),
        ("revenue_leak_estimates", "is_demo"),
        ("remediation_playbooks", "is_demo"),
        ("protection_presets", "is_demo"),
    ]
    for table, column in demo_columns:
        op.add_column(
            table,
            sa.Column(column, sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )


def downgrade() -> None:
    demo_columns = [
        ("protection_presets", "is_demo"),
        ("remediation_playbooks", "is_demo"),
        ("revenue_leak_estimates", "is_demo"),
        ("trust_factor_aggs", "is_demo"),
        ("trust_snapshots", "is_demo"),
        ("incidents", "is_demo"),
        ("ip_enrichments", "is_demo"),
        ("geo_event_aggs", "is_demo"),
        ("security_events", "is_demo"),
        ("behaviour_sessions", "is_demo"),
        ("behaviour_events", "is_demo"),
    ]
    for table, column in demo_columns:
        op.drop_column(table, column)

    op.drop_column("tenants", "demo_expires_at")
    op.drop_column("tenants", "demo_seeded_at")
    op.drop_column("tenants", "is_demo_mode")
