"""create revenue impact tables

Revision ID: ff7b8c9d0e1f
Revises: ff6a7b8c9d0e
Create Date: 2026-01-19 19:20:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ff7b8c9d0e1f"
down_revision: Union[str, None] = "ff6a7b8c9d0e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    json_type = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")

    op.add_column(
        "tenant_settings",
        sa.Column("default_revenue_per_conversion", sa.Float(), nullable=True),
    )

    op.create_table(
        "conversion_metrics",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
        ),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("website_id", sa.Integer(), nullable=True),
        sa.Column("environment_id", sa.Integer(), nullable=True),
        sa.Column("metric_key", sa.String(), nullable=False),
        sa.Column("window_start", sa.DateTime(), nullable=False),
        sa.Column("window_end", sa.DateTime(), nullable=False),
        sa.Column("sessions", sa.Integer(), nullable=False),
        sa.Column("conversions", sa.Integer(), nullable=False),
        sa.Column("conversion_rate", sa.Float(), nullable=False),
        sa.Column("revenue_per_conversion", sa.Float(), nullable=True),
        sa.Column("captured_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["environment_id"], ["website_environments.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "tenant_id",
            "website_id",
            "environment_id",
            "metric_key",
            "window_start",
            "window_end",
            name="uq_conversion_metrics_tenant_metric_window",
        ),
    )
    op.create_index(
        "ix_conversion_metrics_tenant_metric_window",
        "conversion_metrics",
        ["tenant_id", "metric_key", "window_start"],
    )
    op.create_index(
        "ix_conversion_metrics_tenant_site_window",
        "conversion_metrics",
        ["tenant_id", "website_id", "environment_id", "window_start"],
    )

    op.create_table(
        "baseline_models",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
        ),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("website_id", sa.Integer(), nullable=True),
        sa.Column("environment_id", sa.Integer(), nullable=True),
        sa.Column("metric_key", sa.String(), nullable=False),
        sa.Column("baseline_rate", sa.Float(), nullable=False),
        sa.Column("baseline_window_days", sa.Integer(), nullable=False),
        sa.Column("baseline_updated_at", sa.DateTime(), nullable=False),
        sa.Column("method", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["environment_id"], ["website_environments.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "tenant_id",
            "website_id",
            "environment_id",
            "metric_key",
            "method",
            name="uq_baseline_models_tenant_metric_method",
        ),
    )
    op.create_index(
        "ix_baseline_models_tenant_metric",
        "baseline_models",
        ["tenant_id", "metric_key"],
    )
    op.create_index(
        "ix_baseline_models_tenant_site_metric",
        "baseline_models",
        ["tenant_id", "website_id", "environment_id", "metric_key"],
    )

    op.create_table(
        "impact_estimates",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
        ),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("website_id", sa.Integer(), nullable=True),
        sa.Column("environment_id", sa.Integer(), nullable=True),
        sa.Column("metric_key", sa.String(), nullable=False),
        sa.Column("incident_id", sa.String(), nullable=True),
        sa.Column("window_start", sa.DateTime(), nullable=False),
        sa.Column("window_end", sa.DateTime(), nullable=False),
        sa.Column("observed_rate", sa.Float(), nullable=False),
        sa.Column("baseline_rate", sa.Float(), nullable=False),
        sa.Column("delta_rate", sa.Float(), nullable=False),
        sa.Column("estimated_lost_conversions", sa.Float(), nullable=False),
        sa.Column("estimated_lost_revenue", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("explanation_json", json_type, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["environment_id"], ["website_environments.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_impact_estimates_tenant_metric_window",
        "impact_estimates",
        ["tenant_id", "metric_key", "window_start"],
    )
    op.create_index(
        "ix_impact_estimates_tenant_incident",
        "impact_estimates",
        ["tenant_id", "incident_id"],
    )
    op.create_index(
        "ix_impact_estimates_tenant_site_window",
        "impact_estimates",
        ["tenant_id", "website_id", "environment_id", "window_start"],
    )


def downgrade() -> None:
    op.drop_index("ix_impact_estimates_tenant_site_window", table_name="impact_estimates")
    op.drop_index("ix_impact_estimates_tenant_incident", table_name="impact_estimates")
    op.drop_index("ix_impact_estimates_tenant_metric_window", table_name="impact_estimates")
    op.drop_table("impact_estimates")

    op.drop_index("ix_baseline_models_tenant_site_metric", table_name="baseline_models")
    op.drop_index("ix_baseline_models_tenant_metric", table_name="baseline_models")
    op.drop_table("baseline_models")

    op.drop_index("ix_conversion_metrics_tenant_site_window", table_name="conversion_metrics")
    op.drop_index("ix_conversion_metrics_tenant_metric_window", table_name="conversion_metrics")
    op.drop_table("conversion_metrics")

    op.drop_column("tenant_settings", "default_revenue_per_conversion")
