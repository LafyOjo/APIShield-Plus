"""create marketplace templates

Revision ID: fffff3c4d5e6
Revises: fffff2a3b4c5
Create Date: 2026-02-01 10:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "fffff3c4d5e6"
down_revision = "fffff2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "marketplace_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("template_type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("stack_type", sa.String(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("author_user_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(), nullable=False, server_default="community"),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("safety_notes", sa.Text(), nullable=True),
        sa.Column("downloads_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_marketplace_templates_type", "marketplace_templates", ["template_type"], unique=False)
    op.create_index("ix_marketplace_templates_status", "marketplace_templates", ["status"], unique=False)
    op.create_index("ix_marketplace_templates_source", "marketplace_templates", ["source"], unique=False)
    op.create_index("ix_marketplace_templates_stack", "marketplace_templates", ["stack_type"], unique=False)

    op.create_table(
        "template_import_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("imported_at", sa.DateTime(), nullable=False),
        sa.Column("applied_to_incident_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["template_id"], ["marketplace_templates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["applied_to_incident_id"], ["incidents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_template_import_events_tenant", "template_import_events", ["tenant_id"], unique=False)
    op.create_index("ix_template_import_events_template", "template_import_events", ["template_id"], unique=False)
    op.create_index("ix_template_import_events_imported", "template_import_events", ["imported_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_template_import_events_imported", table_name="template_import_events")
    op.drop_index("ix_template_import_events_template", table_name="template_import_events")
    op.drop_index("ix_template_import_events_tenant", table_name="template_import_events")
    op.drop_table("template_import_events")

    op.drop_index("ix_marketplace_templates_stack", table_name="marketplace_templates")
    op.drop_index("ix_marketplace_templates_source", table_name="marketplace_templates")
    op.drop_index("ix_marketplace_templates_status", table_name="marketplace_templates")
    op.drop_index("ix_marketplace_templates_type", table_name="marketplace_templates")
    op.drop_table("marketplace_templates")
