"""add tenant indexes

Revision ID: f2e3d4c5b6a7
Revises: e6f7a8b9c0d1
Create Date: 2026-01-15 06:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f2e3d4c5b6a7"
down_revision: Union[str, None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_memberships_tenant_id", "memberships", ["tenant_id"], unique=False)
    op.create_index("ix_websites_tenant_id", "websites", ["tenant_id"], unique=False)
    op.create_index("ix_api_keys_tenant_id", "api_keys", ["tenant_id"], unique=False)
    op.create_index(
        "ix_invites_tenant_email",
        "invites",
        ["tenant_id", "email"],
        unique=False,
    )
    op.create_index(
        "ix_invites_tenant_expires_at",
        "invites",
        ["tenant_id", "expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_domain_verifications_tenant_website",
        "domain_verifications",
        ["tenant_id", "website_id"],
        unique=False,
    )
    op.drop_index("ix_invites_email", table_name="invites")


def downgrade() -> None:
    op.create_index("ix_invites_email", "invites", ["email"], unique=False)
    op.drop_index("ix_domain_verifications_tenant_website", table_name="domain_verifications")
    op.drop_index("ix_invites_tenant_expires_at", table_name="invites")
    op.drop_index("ix_invites_tenant_email", table_name="invites")
    op.drop_index("ix_api_keys_tenant_id", table_name="api_keys")
    op.drop_index("ix_websites_tenant_id", table_name="websites")
    op.drop_index("ix_memberships_tenant_id", table_name="memberships")
