"""add created_by_user_id to websites and domain_verifications

Revision ID: f6c7d8e9f0a1
Revises: f5b6c7d8e9f0
Create Date: 2026-01-16 14:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f6c7d8e9f0a1"
down_revision: Union[str, None] = "f5b6c7d8e9f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("websites") as batch_op:
        batch_op.add_column(sa.Column("created_by_user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_websites_created_by_user_id",
            "users",
            ["created_by_user_id"],
            ["id"],
        )

    with op.batch_alter_table("domain_verifications") as batch_op:
        batch_op.add_column(sa.Column("created_by_user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_domain_verifications_created_by_user_id",
            "users",
            ["created_by_user_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("domain_verifications") as batch_op:
        batch_op.drop_constraint("fk_domain_verifications_created_by_user_id", type_="foreignkey")
        batch_op.drop_column("created_by_user_id")

    with op.batch_alter_table("websites") as batch_op:
        batch_op.drop_constraint("fk_websites_created_by_user_id", type_="foreignkey")
        batch_op.drop_column("created_by_user_id")
