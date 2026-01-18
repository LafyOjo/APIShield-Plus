"""create project tags tables

Revision ID: c7d8e9f0a1b2
Revises: b4c5d6e7f809
Create Date: 2026-01-15 03:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, None] = "b4c5d6e7f809"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_tags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("color", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_project_tags_tenant_name"),
    )
    op.create_index(op.f("ix_project_tags_id"), "project_tags", ["id"], unique=False)
    op.create_index(op.f("ix_project_tags_tenant_id"), "project_tags", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_project_tags_name"), "project_tags", ["name"], unique=False)

    op.create_table(
        "website_tags",
        sa.Column("website_id", sa.Integer(), sa.ForeignKey("websites.id"), primary_key=True),
        sa.Column("tag_id", sa.Integer(), sa.ForeignKey("project_tags.id"), primary_key=True),
    )
    op.create_index(op.f("ix_website_tags_website_id"), "website_tags", ["website_id"], unique=False)
    op.create_index(op.f("ix_website_tags_tag_id"), "website_tags", ["tag_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_website_tags_tag_id"), table_name="website_tags")
    op.drop_index(op.f("ix_website_tags_website_id"), table_name="website_tags")
    op.drop_table("website_tags")
    op.drop_index(op.f("ix_project_tags_name"), table_name="project_tags")
    op.drop_index(op.f("ix_project_tags_tenant_id"), table_name="project_tags")
    op.drop_index(op.f("ix_project_tags_id"), table_name="project_tags")
    op.drop_table("project_tags")
