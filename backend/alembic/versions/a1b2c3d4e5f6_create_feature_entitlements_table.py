"""create feature entitlements table

Revision ID: a1b2c3d4e5f6
Revises: 9f1a0b2c3d4e
Create Date: 2026-01-15 02:05:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "9f1a0b2c3d4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "feature_entitlements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("feature", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("source_plan_id", sa.Integer(), sa.ForeignKey("plans.id"), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "feature", name="uq_feature_entitlement"),
    )
    op.create_index(op.f("ix_feature_entitlements_id"), "feature_entitlements", ["id"], unique=False)
    op.create_index(op.f("ix_feature_entitlements_tenant_id"), "feature_entitlements", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_feature_entitlements_feature"), "feature_entitlements", ["feature"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_feature_entitlements_feature"), table_name="feature_entitlements")
    op.drop_index(op.f("ix_feature_entitlements_tenant_id"), table_name="feature_entitlements")
    op.drop_index(op.f("ix_feature_entitlements_id"), table_name="feature_entitlements")
    op.drop_table("feature_entitlements")
