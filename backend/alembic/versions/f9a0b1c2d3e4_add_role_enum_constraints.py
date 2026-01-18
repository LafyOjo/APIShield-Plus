"""add role and membership status check constraints

Revision ID: f9a0b1c2d3e4
Revises: f8e9f0a1b2c3
Create Date: 2026-01-16 20:30:00.000000
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f9a0b1c2d3e4"
down_revision: Union[str, None] = "f8e9f0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("memberships") as batch_op:
        batch_op.create_check_constraint(
            "membership_role_enum",
            "role IN ('owner', 'admin', 'analyst', 'viewer')",
        )
        batch_op.create_check_constraint(
            "membership_status_enum",
            "status IN ('active', 'invited', 'suspended')",
        )

    with op.batch_alter_table("invites") as batch_op:
        batch_op.create_check_constraint(
            "invite_role_enum",
            "role IN ('owner', 'admin', 'analyst', 'viewer')",
        )


def downgrade() -> None:
    with op.batch_alter_table("invites") as batch_op:
        batch_op.drop_constraint("invite_role_enum", type_="check")

    with op.batch_alter_table("memberships") as batch_op:
        batch_op.drop_constraint("membership_status_enum", type_="check")
        batch_op.drop_constraint("membership_role_enum", type_="check")
