"""expand role enum constraints for new role templates

Revision ID: ffff0b1c2d3e
Revises: f9a0b1c2d3e4
Create Date: 2026-01-23 18:20:00.000000
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ffff0b1c2d3e"
down_revision: Union[str, None] = "f9a0b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("memberships") as batch_op:
        batch_op.drop_constraint("membership_role_enum", type_="check")
        batch_op.create_check_constraint(
            "membership_role_enum",
            "role IN ('owner', 'admin', 'security_admin', 'billing_admin', 'analyst', 'viewer')",
        )

    with op.batch_alter_table("invites") as batch_op:
        batch_op.drop_constraint("invite_role_enum", type_="check")
        batch_op.create_check_constraint(
            "invite_role_enum",
            "role IN ('owner', 'admin', 'security_admin', 'billing_admin', 'analyst', 'viewer')",
        )


def downgrade() -> None:
    with op.batch_alter_table("invites") as batch_op:
        batch_op.drop_constraint("invite_role_enum", type_="check")
        batch_op.create_check_constraint(
            "invite_role_enum",
            "role IN ('owner', 'admin', 'analyst', 'viewer')",
        )

    with op.batch_alter_table("memberships") as batch_op:
        batch_op.drop_constraint("membership_role_enum", type_="check")
        batch_op.create_check_constraint(
            "membership_role_enum",
            "role IN ('owner', 'admin', 'analyst', 'viewer')",
        )
