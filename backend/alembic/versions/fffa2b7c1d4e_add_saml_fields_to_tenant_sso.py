"""add saml fields to tenant sso config

Revision ID: fffa2b7c1d4e
Revises: fff9d0e1f2a3
Create Date: 2026-01-23 16:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "fffa2b7c1d4e"
down_revision: Union[str, None] = "fff9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("tenant_sso_configs") as batch:
        batch.alter_column("issuer_url", existing_type=sa.String(), nullable=True)
        batch.alter_column("client_id", existing_type=sa.String(), nullable=True)
        batch.alter_column("client_secret_enc", existing_type=sa.Text(), nullable=True)
        batch.alter_column("redirect_uri", existing_type=sa.String(), nullable=True)
        batch.alter_column("scopes", existing_type=sa.String(), nullable=True)
        batch.add_column(sa.Column("idp_entity_id", sa.String(), nullable=True))
        batch.add_column(sa.Column("idp_sso_url", sa.String(), nullable=True))
        batch.add_column(sa.Column("idp_x509_cert", sa.Text(), nullable=True))
        batch.add_column(sa.Column("sp_entity_id", sa.String(), nullable=True))
        batch.add_column(sa.Column("sp_acs_url", sa.String(), nullable=True))
        batch.add_column(sa.Column("sp_x509_cert", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("tenant_sso_configs") as batch:
        batch.drop_column("sp_x509_cert")
        batch.drop_column("sp_acs_url")
        batch.drop_column("sp_entity_id")
        batch.drop_column("idp_x509_cert")
        batch.drop_column("idp_sso_url")
        batch.drop_column("idp_entity_id")
        batch.alter_column("scopes", existing_type=sa.String(), nullable=False)
        batch.alter_column("redirect_uri", existing_type=sa.String(), nullable=False)
        batch.alter_column("client_secret_enc", existing_type=sa.Text(), nullable=False)
        batch.alter_column("client_id", existing_type=sa.String(), nullable=False)
        batch.alter_column("issuer_url", existing_type=sa.String(), nullable=False)
