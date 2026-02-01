"""create integration directory tables

Revision ID: fffff2a3b4c5
Revises: fffff1d2e3f4
Create Date: 2026-02-01 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "fffff2a3b4c5"
down_revision = "fffff1d2e3f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_listings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("docs_url", sa.String(), nullable=True),
        sa.Column("install_type", sa.String(), nullable=False),
        sa.Column("is_featured", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("plan_required", sa.String(), nullable=True),
        sa.Column("install_url", sa.String(), nullable=True),
        sa.Column("copy_payload", sa.Text(), nullable=True),
        sa.Column("stack_types", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index("ix_integration_listings_key", "integration_listings", ["key"], unique=True)
    op.create_index("ix_integration_listings_category", "integration_listings", ["category"], unique=False)
    op.create_index("ix_integration_listings_featured", "integration_listings", ["is_featured"], unique=False)

    op.create_table(
        "integration_install_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("website_id", sa.Integer(), nullable=True),
        sa.Column("integration_key", sa.String(), nullable=False),
        sa.Column("installed_at", sa.DateTime(), nullable=False),
        sa.Column("method", sa.String(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_integration_installs_tenant", "integration_install_events", ["tenant_id"], unique=False)
    op.create_index("ix_integration_installs_key", "integration_install_events", ["integration_key"], unique=False)
    op.create_index("ix_integration_installs_installed", "integration_install_events", ["installed_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_integration_installs_installed", table_name="integration_install_events")
    op.drop_index("ix_integration_installs_key", table_name="integration_install_events")
    op.drop_index("ix_integration_installs_tenant", table_name="integration_install_events")
    op.drop_table("integration_install_events")

    op.drop_index("ix_integration_listings_featured", table_name="integration_listings")
    op.drop_index("ix_integration_listings_category", table_name="integration_listings")
    op.drop_index("ix_integration_listings_key", table_name="integration_listings")
    op.drop_table("integration_listings")
