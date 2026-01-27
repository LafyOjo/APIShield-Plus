"""create scim config and mapping tables

Revision ID: fffe6f7a8b9c
Revises: fffd5e6f7a8b
Create Date: 2026-01-23 19:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "fffe6f7a8b9c"
down_revision = "fffd5e6f7a8b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_scim_configs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("scim_token_hash", sa.String(), nullable=True),
        sa.Column("token_last_rotated_at", sa.DateTime(), nullable=True),
        sa.Column("default_role", sa.String(), nullable=False, server_default=sa.text("'viewer'")),
        sa.Column("group_role_mappings_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", name="uq_tenant_scim_config_tenant"),
    )
    op.create_index(
        "ix_tenant_scim_config_tenant_enabled",
        "tenant_scim_configs",
        ["tenant_id", "is_enabled"],
    )
    op.create_index(
        "ix_tenant_scim_configs_tenant_id",
        "tenant_scim_configs",
        ["tenant_id"],
    )

    op.create_table(
        "scim_external_user_maps",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("scim_user_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "tenant_id",
            "scim_user_id",
            name="uq_scim_user_map_tenant_scim_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "user_id",
            name="uq_scim_user_map_tenant_user",
        ),
    )
    op.create_index(
        "ix_scim_user_map_tenant",
        "scim_external_user_maps",
        ["tenant_id"],
    )
    op.create_index(
        "ix_scim_external_user_maps_user_id",
        "scim_external_user_maps",
        ["user_id"],
    )

    op.create_table(
        "scim_external_group_maps",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("scim_group_id", sa.String(), nullable=False),
        sa.Column("tenant_role", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "tenant_id",
            "scim_group_id",
            name="uq_scim_group_map_tenant_scim_id",
        ),
    )
    op.create_index(
        "ix_scim_group_map_tenant",
        "scim_external_group_maps",
        ["tenant_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_scim_group_map_tenant", table_name="scim_external_group_maps")
    op.drop_table("scim_external_group_maps")
    op.drop_index("ix_scim_external_user_maps_user_id", table_name="scim_external_user_maps")
    op.drop_index("ix_scim_user_map_tenant", table_name="scim_external_user_maps")
    op.drop_table("scim_external_user_maps")
    op.drop_index("ix_tenant_scim_configs_tenant_id", table_name="tenant_scim_configs")
    op.drop_index("ix_tenant_scim_config_tenant_enabled", table_name="tenant_scim_configs")
    op.drop_table("tenant_scim_configs")
