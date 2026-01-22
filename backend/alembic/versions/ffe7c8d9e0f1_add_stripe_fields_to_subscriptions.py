"""add stripe fields to subscriptions table

Revision ID: ffe7c8d9e0f1
Revises: ffe6b7c8d9e0
Create Date: 2026-01-21 15:12:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "ffe7c8d9e0f1"
down_revision = "ffe6b7c8d9e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("plan_key", sa.String(), nullable=True))
    op.add_column("subscriptions", sa.Column("stripe_customer_id", sa.String(), nullable=True))
    op.add_column("subscriptions", sa.Column("stripe_subscription_id", sa.String(), nullable=True))
    op.add_column("subscriptions", sa.Column("seats", sa.Integer(), nullable=True))
    op.create_index("ix_subscriptions_plan_key", "subscriptions", ["plan_key"])
    op.create_index(
        "ix_subscriptions_stripe_customer",
        "subscriptions",
        ["stripe_customer_id"],
    )
    op.create_index(
        "ix_subscriptions_stripe_subscription",
        "subscriptions",
        ["stripe_subscription_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_subscriptions_stripe_subscription", table_name="subscriptions")
    op.drop_index("ix_subscriptions_stripe_customer", table_name="subscriptions")
    op.drop_index("ix_subscriptions_plan_key", table_name="subscriptions")
    op.drop_column("subscriptions", "seats")
    op.drop_column("subscriptions", "stripe_subscription_id")
    op.drop_column("subscriptions", "stripe_customer_id")
    op.drop_column("subscriptions", "plan_key")
