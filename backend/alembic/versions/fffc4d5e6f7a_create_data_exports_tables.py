"""create data export config/run tables

Revision ID: fffc4d5e6f7a
Revises: fffb3c4d5e6f
Create Date: 2026-01-23 18:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "fffc4d5e6f7a"
down_revision = "fffb3c4d5e6f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_export_configs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_secret_enc", sa.Text(), nullable=True),
        sa.Column("schedule", sa.String(), nullable=False, server_default=sa.text("'daily'")),
        sa.Column("datasets_enabled", sa.JSON(), nullable=False),
        sa.Column("format", sa.String(), nullable=False, server_default=sa.text("'jsonl.gz'")),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", name="uq_data_export_configs_tenant"),
    )
    op.create_index(
        "ix_data_export_configs_tenant_enabled",
        "data_export_configs",
        ["tenant_id", "is_enabled"],
    )
    op.create_index(
        "ix_data_export_configs_tenant_id",
        "data_export_configs",
        ["tenant_id"],
    )

    op.create_table(
        "data_export_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("config_id", sa.BigInteger(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("files_written", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bytes_written", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["config_id"], ["data_export_configs.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_data_export_runs_tenant_started_at",
        "data_export_runs",
        ["tenant_id", "started_at"],
    )
    op.create_index(
        "ix_data_export_runs_config_started_at",
        "data_export_runs",
        ["config_id", "started_at"],
    )
    op.create_index(
        "ix_data_export_runs_tenant_id",
        "data_export_runs",
        ["tenant_id"],
    )
    op.create_index(
        "ix_data_export_runs_config_id",
        "data_export_runs",
        ["config_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_data_export_runs_config_id", table_name="data_export_runs")
    op.drop_index("ix_data_export_runs_tenant_id", table_name="data_export_runs")
    op.drop_index("ix_data_export_runs_config_started_at", table_name="data_export_runs")
    op.drop_index("ix_data_export_runs_tenant_started_at", table_name="data_export_runs")
    op.drop_table("data_export_runs")
    op.drop_index("ix_data_export_configs_tenant_id", table_name="data_export_configs")
    op.drop_index("ix_data_export_configs_tenant_enabled", table_name="data_export_configs")
    op.drop_table("data_export_configs")
