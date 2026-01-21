"""create incidents and links

Revision ID: ff8c9d0e1f2a
Revises: ff7b8c9d0e1f
Create Date: 2026-01-19 20:10:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ff8c9d0e1f2a"
down_revision: Union[str, None] = "ff7b8c9d0e1f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    json_type = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")
    op.create_table(
        "incidents",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
        ),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("website_id", sa.Integer(), nullable=True),
        sa.Column("environment_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("summary", sa.String(), nullable=True),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("primary_ip_hash", sa.String(), nullable=True),
        sa.Column("primary_country_code", sa.String(), nullable=True),
        sa.Column("evidence_json", json_type, nullable=True),
        sa.Column(
            "impact_estimate_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            nullable=True,
        ),
        sa.Column("prescription_bundle_id", sa.String(), nullable=True),
        sa.Column("assigned_to_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["environment_id"], ["website_environments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["impact_estimate_id"], ["impact_estimates.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_to_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_incidents_tenant_status_last_seen",
        "incidents",
        ["tenant_id", "status", "last_seen_at"],
    )
    op.create_index(
        "ix_incidents_tenant_category_last_seen",
        "incidents",
        ["tenant_id", "category", "last_seen_at"],
    )
    op.create_index(
        "ix_incidents_tenant_site_last_seen",
        "incidents",
        ["tenant_id", "website_id", "environment_id", "last_seen_at"],
    )
    op.create_index(
        "ix_incidents_tenant_impact",
        "incidents",
        ["tenant_id", "impact_estimate_id"],
    )

    op.create_table(
        "incident_security_event_links",
        sa.Column(
            "incident_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
        ),
        sa.Column(
            "security_event_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["security_event_id"], ["security_events.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_incident_security_event_links_incident_id",
        "incident_security_event_links",
        ["incident_id"],
    )
    op.create_index(
        "ix_incident_security_event_links_security_event_id",
        "incident_security_event_links",
        ["security_event_id"],
    )

    op.create_table(
        "incident_anomaly_signal_links",
        sa.Column(
            "incident_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
        ),
        sa.Column(
            "anomaly_signal_id",
            sa.Integer(),
            primary_key=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["anomaly_signal_id"],
            ["anomaly_signal_events.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_incident_anomaly_signal_links_incident_id",
        "incident_anomaly_signal_links",
        ["incident_id"],
    )
    op.create_index(
        "ix_incident_anomaly_signal_links_signal_id",
        "incident_anomaly_signal_links",
        ["anomaly_signal_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_incident_anomaly_signal_links_signal_id",
        table_name="incident_anomaly_signal_links",
    )
    op.drop_index(
        "ix_incident_anomaly_signal_links_incident_id",
        table_name="incident_anomaly_signal_links",
    )
    op.drop_table("incident_anomaly_signal_links")

    op.drop_index(
        "ix_incident_security_event_links_security_event_id",
        table_name="incident_security_event_links",
    )
    op.drop_index(
        "ix_incident_security_event_links_incident_id",
        table_name="incident_security_event_links",
    )
    op.drop_table("incident_security_event_links")

    op.drop_index("ix_incidents_tenant_impact", table_name="incidents")
    op.drop_index("ix_incidents_tenant_site_last_seen", table_name="incidents")
    op.drop_index("ix_incidents_tenant_category_last_seen", table_name="incidents")
    op.drop_index("ix_incidents_tenant_status_last_seen", table_name="incidents")
    op.drop_table("incidents")
