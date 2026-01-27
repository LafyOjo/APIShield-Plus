\"\"\"create protection presets

Revision ID: ffff9f0a1b2c
Revises: ffff8e9f0abc
Create Date: 2026-01-25 14:45:00.000000
\"\"\"

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "ffff9f0a1b2c"
down_revision = "ffff8e9f0abc"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "protection_presets",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("website_id", sa.Integer(), nullable=True),
        sa.Column("incident_id", sa.Integer(), nullable=False),
        sa.Column("preset_type", sa.String(), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", "incident_id", "preset_type", name="uq_preset_incident_type"),
    )
    op.create_index("ix_presets_tenant_incident", "protection_presets", ["tenant_id", "incident_id"])
    op.create_index("ix_presets_tenant_created", "protection_presets", ["tenant_id", "created_at"])
    op.create_index("ix_protection_presets_tenant_id", "protection_presets", ["tenant_id"])
    op.create_index("ix_protection_presets_incident_id", "protection_presets", ["incident_id"])
    op.create_index("ix_protection_presets_website_id", "protection_presets", ["website_id"])
    op.create_index("ix_protection_presets_preset_type", "protection_presets", ["preset_type"])


def downgrade():
    op.drop_index("ix_protection_presets_preset_type", table_name="protection_presets")
    op.drop_index("ix_protection_presets_website_id", table_name="protection_presets")
    op.drop_index("ix_protection_presets_incident_id", table_name="protection_presets")
    op.drop_index("ix_protection_presets_tenant_id", table_name="protection_presets")
    op.drop_index("ix_presets_tenant_created", table_name="protection_presets")
    op.drop_index("ix_presets_tenant_incident", table_name="protection_presets")
    op.drop_table("protection_presets")
