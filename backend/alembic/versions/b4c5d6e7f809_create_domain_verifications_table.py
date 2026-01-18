"""create domain verifications table

Revision ID: b4c5d6e7f809
Revises: a1b2c3d4e5f6
Create Date: 2026-01-15 02:45:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b4c5d6e7f809"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "domain_verifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("website_id", sa.Integer(), sa.ForeignKey("websites.id"), nullable=False),
        sa.Column("method", sa.String(), nullable=False),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
    )
    op.create_index(op.f("ix_domain_verifications_id"), "domain_verifications", ["id"], unique=False)
    op.create_index(
        op.f("ix_domain_verifications_tenant_id"),
        "domain_verifications",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_domain_verifications_website_id"),
        "domain_verifications",
        ["website_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_domain_verifications_method"),
        "domain_verifications",
        ["method"],
        unique=False,
    )
    op.create_index(
        op.f("ix_domain_verifications_token"),
        "domain_verifications",
        ["token"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_domain_verifications_token"), table_name="domain_verifications")
    op.drop_index(op.f("ix_domain_verifications_method"), table_name="domain_verifications")
    op.drop_index(op.f("ix_domain_verifications_website_id"), table_name="domain_verifications")
    op.drop_index(op.f("ix_domain_verifications_tenant_id"), table_name="domain_verifications")
    op.drop_index(op.f("ix_domain_verifications_id"), table_name="domain_verifications")
    op.drop_table("domain_verifications")
