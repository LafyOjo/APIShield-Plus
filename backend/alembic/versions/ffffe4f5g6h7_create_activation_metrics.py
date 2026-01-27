"""create activation metrics

Revision ID: ffffe4f5g6h7
Revises: ffffd3e4f5g6
Create Date: 2026-01-26 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "ffffe4f5g6h7"
down_revision = "ffffd3e4f5g6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "activation_metrics",
        sa.Column("tenant_id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("time_to_first_event_seconds", sa.Integer(), nullable=True),
        sa.Column("onboarding_completed_at", sa.DateTime(), nullable=True),
        sa.Column("first_alert_created_at", sa.DateTime(), nullable=True),
        sa.Column("first_incident_viewed_at", sa.DateTime(), nullable=True),
        sa.Column("first_prescription_applied_at", sa.DateTime(), nullable=True),
        sa.Column("activation_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_activation_metrics_score",
        "activation_metrics",
        ["activation_score"],
    )


def downgrade():
    op.drop_index("ix_activation_metrics_score", table_name="activation_metrics")
    op.drop_table("activation_metrics")
