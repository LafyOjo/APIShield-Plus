"""create feature flags and experiments

Revision ID: fffff9b0c2d3
Revises: fffff8a9b0c1
Create Date: 2026-01-30 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "fffff9b0c2d3"
down_revision = "fffff8a9b0c1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "feature_flags",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("is_enabled_global", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("rules_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("key", name="uq_feature_flags_key"),
    )

    op.create_table(
        "experiments",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("variants_json", sa.JSON(), nullable=False),
        sa.Column("targeting_rules_json", sa.JSON(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("key", name="uq_experiments_key"),
    )

    op.create_table(
        "experiment_assignments",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("experiment_key", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("variant", sa.String(), nullable=False),
        sa.Column("assigned_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "experiment_key",
            "tenant_id",
            "user_id",
            name="uq_experiment_assignments",
        ),
    )
    op.create_index(
        "ix_experiment_assignments_experiment",
        "experiment_assignments",
        ["experiment_key"],
    )
    op.create_index(
        "ix_experiment_assignments_tenant",
        "experiment_assignments",
        ["tenant_id"],
    )

    op.alter_column("feature_flags", "is_enabled_global", server_default=None)
    op.alter_column("experiments", "is_enabled", server_default=None)


def downgrade():
    op.drop_index("ix_experiment_assignments_tenant", table_name="experiment_assignments")
    op.drop_index("ix_experiment_assignments_experiment", table_name="experiment_assignments")
    op.drop_table("experiment_assignments")
    op.drop_table("experiments")
    op.drop_table("feature_flags")
