"""add is_platform_admin to users

Revision ID: fffd5e6f7a8b
Revises: fffc4d5e6f7a
Create Date: 2026-01-23 19:05:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "fffd5e6f7a8b"
down_revision = "fffc4d5e6f7a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_platform_admin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "is_platform_admin")
