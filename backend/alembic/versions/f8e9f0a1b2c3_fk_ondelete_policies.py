"""add fk ondelete policies for audit fields and join tables

Revision ID: f8e9f0a1b2c3
Revises: f7d8e9f0a1b2
Create Date: 2026-01-16 16:15:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "f8e9f0a1b2c3"
down_revision: Union[str, None] = "f7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_fk_name(conn, table: str, column: str, referred_table: str) -> str | None:
    inspector = inspect(conn)
    for fk in inspector.get_foreign_keys(table):
        if fk["constrained_columns"] == [column] and fk["referred_table"] == referred_table:
            return fk["name"]
    return None


def _replace_fk(
    conn,
    table: str,
    column: str,
    referred_table: str,
    ondelete: str,
    name: str,
) -> None:
    fk_name = _get_fk_name(conn, table, column, referred_table)
    if fk_name:
        op.drop_constraint(fk_name, table_name=table, type_="foreignkey")
    op.create_foreign_key(name, table, referred_table, [column], ["id"], ondelete=ondelete)


def _sqlite_rebuild_table(
    conn,
    table_name: str,
    columns: list[sa.Column],
    constraints: list,
    indexes: list[tuple[str, list[str], bool]],
) -> None:
    tmp_name = f"{table_name}__tmp"
    op.create_table(tmp_name, *columns, *constraints)
    column_names = ", ".join(col.name for col in columns)
    conn.execute(
        sa.text(f"INSERT INTO {tmp_name} ({column_names}) SELECT {column_names} FROM {table_name}")
    )
    op.drop_table(table_name)
    op.rename_table(tmp_name, table_name)
    for name, cols, unique in indexes:
        op.create_index(name, table_name, cols, unique=unique)


def upgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name

    if dialect == "sqlite":
        conn.execute(sa.text("PRAGMA foreign_keys=OFF"))

        _sqlite_rebuild_table(
            conn,
            "tenants",
            [
                sa.Column("id", sa.Integer(), primary_key=True),
                sa.Column("name", sa.String(), nullable=False),
                sa.Column("slug", sa.String(), nullable=False),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=False),
                sa.Column("deleted_at", sa.DateTime(), nullable=True),
                sa.Column(
                    "created_by_user_id",
                    sa.Integer(),
                    sa.ForeignKey("users.id", ondelete="SET NULL"),
                    nullable=True,
                ),
            ],
            [],
            [
                ("ix_tenants_id", ["id"], False),
                ("ix_tenants_slug", ["slug"], True),
            ],
        )

        _sqlite_rebuild_table(
            conn,
            "websites",
            [
                sa.Column("id", sa.Integer(), primary_key=True),
                sa.Column(
                    "tenant_id",
                    sa.Integer(),
                    sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
                    nullable=False,
                ),
                sa.Column("domain", sa.String(), nullable=False),
                sa.Column("display_name", sa.String(), nullable=True),
                sa.Column("status", sa.String(), nullable=False),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=False),
                sa.Column("deleted_at", sa.DateTime(), nullable=True),
                sa.Column(
                    "created_by_user_id",
                    sa.Integer(),
                    sa.ForeignKey("users.id", ondelete="SET NULL"),
                    nullable=True,
                ),
            ],
            [
                sa.UniqueConstraint("tenant_id", "domain", name="uq_websites_tenant_domain"),
            ],
            [
                ("ix_websites_id", ["id"], False),
                ("ix_websites_tenant_created_at", ["tenant_id", "created_at"], False),
                ("ix_websites_tenant_id", ["tenant_id"], False),
            ],
        )

        _sqlite_rebuild_table(
            conn,
            "api_keys",
            [
                sa.Column("id", sa.Integer(), primary_key=True),
                sa.Column(
                    "tenant_id",
                    sa.Integer(),
                    sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
                    nullable=False,
                ),
                sa.Column(
                    "website_id",
                    sa.Integer(),
                    sa.ForeignKey("websites.id", ondelete="RESTRICT"),
                    nullable=False,
                ),
                sa.Column(
                    "environment_id",
                    sa.Integer(),
                    sa.ForeignKey("website_environments.id", ondelete="RESTRICT"),
                    nullable=False,
                ),
                sa.Column("public_key", sa.String(), nullable=False),
                sa.Column("secret_hash", sa.String(), nullable=False),
                sa.Column("name", sa.String(), nullable=True),
                sa.Column("status", sa.String(), nullable=False, server_default="active"),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=False),
                sa.Column(
                    "created_by_user_id",
                    sa.Integer(),
                    sa.ForeignKey("users.id", ondelete="SET NULL"),
                    nullable=True,
                ),
                sa.Column("last_used_at", sa.DateTime(), nullable=True),
                sa.Column("revoked_at", sa.DateTime(), nullable=True),
                sa.Column(
                    "revoked_by_user_id",
                    sa.Integer(),
                    sa.ForeignKey("users.id", ondelete="SET NULL"),
                    nullable=True,
                ),
            ],
            [],
            [
                ("ix_api_keys_id", ["id"], False),
                ("ix_api_keys_public_key", ["public_key"], True),
                ("ix_api_keys_tenant_environment", ["tenant_id", "environment_id"], False),
                ("ix_api_keys_tenant_created_at", ["tenant_id", "created_at"], False),
                ("ix_api_keys_tenant_id", ["tenant_id"], False),
            ],
        )

        _sqlite_rebuild_table(
            conn,
            "memberships",
            [
                sa.Column("id", sa.Integer(), primary_key=True),
                sa.Column(
                    "tenant_id",
                    sa.Integer(),
                    sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
                    nullable=False,
                ),
                sa.Column(
                    "user_id",
                    sa.Integer(),
                    sa.ForeignKey("users.id", ondelete="RESTRICT"),
                    nullable=False,
                ),
                sa.Column("role", sa.String(), nullable=False),
                sa.Column("status", sa.String(), nullable=False),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=False),
                sa.Column(
                    "created_by_user_id",
                    sa.Integer(),
                    sa.ForeignKey("users.id", ondelete="SET NULL"),
                    nullable=True,
                ),
            ],
            [
                sa.UniqueConstraint("tenant_id", "user_id", name="uq_membership_user_tenant"),
            ],
            [
                ("ix_memberships_id", ["id"], False),
                ("ix_memberships_tenant_role", ["tenant_id", "role"], False),
                ("ix_memberships_user_id", ["user_id"], False),
                ("ix_memberships_tenant_id", ["tenant_id"], False),
            ],
        )

        _sqlite_rebuild_table(
            conn,
            "invites",
            [
                sa.Column("id", sa.Integer(), primary_key=True),
                sa.Column(
                    "tenant_id",
                    sa.Integer(),
                    sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
                    nullable=False,
                ),
                sa.Column("email", sa.String(), nullable=False),
                sa.Column("role", sa.String(), nullable=False),
                sa.Column("token_hash", sa.String(), nullable=False),
                sa.Column("expires_at", sa.DateTime(), nullable=False),
                sa.Column("accepted_at", sa.DateTime(), nullable=True),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=False),
                sa.Column(
                    "created_by_user_id",
                    sa.Integer(),
                    sa.ForeignKey("users.id", ondelete="SET NULL"),
                    nullable=True,
                ),
            ],
            [],
            [
                ("ix_invites_id", ["id"], False),
                ("ix_invites_tenant_id", ["tenant_id"], False),
                ("ix_invites_token_hash", ["token_hash"], True),
                ("ix_invites_tenant_email", ["tenant_id", "email"], False),
                ("ix_invites_tenant_expires_at", ["tenant_id", "expires_at"], False),
            ],
        )

        _sqlite_rebuild_table(
            conn,
            "domain_verifications",
            [
                sa.Column("id", sa.Integer(), primary_key=True),
                sa.Column(
                    "tenant_id",
                    sa.Integer(),
                    sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
                    nullable=False,
                ),
                sa.Column(
                    "website_id",
                    sa.Integer(),
                    sa.ForeignKey("websites.id", ondelete="RESTRICT"),
                    nullable=False,
                ),
                sa.Column("method", sa.String(), nullable=False),
                sa.Column("token", sa.String(), nullable=False),
                sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'pending'")),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=False),
                sa.Column(
                    "created_by_user_id",
                    sa.Integer(),
                    sa.ForeignKey("users.id", ondelete="SET NULL"),
                    nullable=True,
                ),
                sa.Column("verified_at", sa.DateTime(), nullable=True),
                sa.Column("last_checked_at", sa.DateTime(), nullable=True),
            ],
            [],
            [
                ("ix_domain_verifications_id", ["id"], False),
                ("ix_domain_verifications_tenant_id", ["tenant_id"], False),
                ("ix_domain_verifications_website_id", ["website_id"], False),
                ("ix_domain_verifications_method", ["method"], False),
                ("ix_domain_verifications_token", ["token"], True),
                ("ix_domain_verifications_tenant_website", ["tenant_id", "website_id"], False),
            ],
        )

        _sqlite_rebuild_table(
            conn,
            "feature_entitlements",
            [
                sa.Column("id", sa.Integer(), primary_key=True),
                sa.Column(
                    "tenant_id",
                    sa.Integer(),
                    sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
                    nullable=False,
                ),
                sa.Column("feature", sa.String(), nullable=False),
                sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
                sa.Column("source", sa.String(), nullable=False),
                sa.Column(
                    "source_plan_id",
                    sa.Integer(),
                    sa.ForeignKey("plans.id", ondelete="RESTRICT"),
                    nullable=True,
                ),
                sa.Column(
                    "updated_by_user_id",
                    sa.Integer(),
                    sa.ForeignKey("users.id", ondelete="SET NULL"),
                    nullable=True,
                ),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=False),
            ],
            [
                sa.UniqueConstraint("tenant_id", "feature", name="uq_feature_entitlement"),
            ],
            [
                ("ix_feature_entitlements_id", ["id"], False),
                ("ix_feature_entitlements_tenant_id", ["tenant_id"], False),
                ("ix_feature_entitlements_feature", ["feature"], False),
            ],
        )

        _sqlite_rebuild_table(
            conn,
            "website_tags",
            [
                sa.Column(
                    "website_id",
                    sa.Integer(),
                    sa.ForeignKey("websites.id", ondelete="CASCADE"),
                    primary_key=True,
                ),
                sa.Column(
                    "tag_id",
                    sa.Integer(),
                    sa.ForeignKey("project_tags.id", ondelete="CASCADE"),
                    primary_key=True,
                ),
            ],
            [],
            [
                ("ix_website_tags_website_id", ["website_id"], False),
                ("ix_website_tags_tag_id", ["tag_id"], False),
            ],
        )

        conn.execute(sa.text("PRAGMA foreign_keys=ON"))
        return

    _replace_fk(
        conn,
        "tenants",
        "created_by_user_id",
        "users",
        "SET NULL",
        "fk_tenants_created_by_user_id",
    )
    _replace_fk(
        conn,
        "websites",
        "created_by_user_id",
        "users",
        "SET NULL",
        "fk_websites_created_by_user_id",
    )
    _replace_fk(
        conn,
        "api_keys",
        "created_by_user_id",
        "users",
        "SET NULL",
        "fk_api_keys_created_by_user_id",
    )
    _replace_fk(
        conn,
        "api_keys",
        "revoked_by_user_id",
        "users",
        "SET NULL",
        "fk_api_keys_revoked_by_user_id",
    )
    _replace_fk(
        conn,
        "memberships",
        "created_by_user_id",
        "users",
        "SET NULL",
        "fk_memberships_created_by_user_id",
    )
    _replace_fk(
        conn,
        "invites",
        "created_by_user_id",
        "users",
        "SET NULL",
        "fk_invites_created_by_user_id",
    )
    _replace_fk(
        conn,
        "domain_verifications",
        "created_by_user_id",
        "users",
        "SET NULL",
        "fk_domain_verifications_created_by_user_id",
    )
    _replace_fk(
        conn,
        "feature_entitlements",
        "updated_by_user_id",
        "users",
        "SET NULL",
        "fk_feature_entitlements_updated_by_user_id",
    )
    _replace_fk(
        conn,
        "website_tags",
        "website_id",
        "websites",
        "CASCADE",
        "fk_website_tags_website_id",
    )
    _replace_fk(
        conn,
        "website_tags",
        "tag_id",
        "project_tags",
        "CASCADE",
        "fk_website_tags_tag_id",
    )

    op.alter_column("invites", "created_by_user_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name

    if dialect == "sqlite":
        conn.execute(sa.text("PRAGMA foreign_keys=OFF"))

        _sqlite_rebuild_table(
            conn,
            "tenants",
            [
                sa.Column("id", sa.Integer(), primary_key=True),
                sa.Column("name", sa.String(), nullable=False),
                sa.Column("slug", sa.String(), nullable=False),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=False),
                sa.Column("deleted_at", sa.DateTime(), nullable=True),
                sa.Column(
                    "created_by_user_id",
                    sa.Integer(),
                    sa.ForeignKey("users.id"),
                    nullable=True,
                ),
            ],
            [],
            [
                ("ix_tenants_id", ["id"], False),
                ("ix_tenants_slug", ["slug"], True),
            ],
        )

        _sqlite_rebuild_table(
            conn,
            "websites",
            [
                sa.Column("id", sa.Integer(), primary_key=True),
                sa.Column(
                    "tenant_id",
                    sa.Integer(),
                    sa.ForeignKey("tenants.id"),
                    nullable=False,
                ),
                sa.Column("domain", sa.String(), nullable=False),
                sa.Column("display_name", sa.String(), nullable=True),
                sa.Column("status", sa.String(), nullable=False),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=False),
                sa.Column("deleted_at", sa.DateTime(), nullable=True),
                sa.Column(
                    "created_by_user_id",
                    sa.Integer(),
                    sa.ForeignKey("users.id"),
                    nullable=True,
                ),
            ],
            [
                sa.UniqueConstraint("tenant_id", "domain", name="uq_websites_tenant_domain"),
            ],
            [
                ("ix_websites_id", ["id"], False),
                ("ix_websites_tenant_created_at", ["tenant_id", "created_at"], False),
                ("ix_websites_tenant_id", ["tenant_id"], False),
            ],
        )

        _sqlite_rebuild_table(
            conn,
            "api_keys",
            [
                sa.Column("id", sa.Integer(), primary_key=True),
                sa.Column(
                    "tenant_id",
                    sa.Integer(),
                    sa.ForeignKey("tenants.id"),
                    nullable=False,
                ),
                sa.Column(
                    "website_id",
                    sa.Integer(),
                    sa.ForeignKey("websites.id"),
                    nullable=False,
                ),
                sa.Column(
                    "environment_id",
                    sa.Integer(),
                    sa.ForeignKey("website_environments.id"),
                    nullable=False,
                ),
                sa.Column("public_key", sa.String(), nullable=False),
                sa.Column("secret_hash", sa.String(), nullable=False),
                sa.Column("name", sa.String(), nullable=True),
                sa.Column("status", sa.String(), nullable=False, server_default="active"),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=False),
                sa.Column(
                    "created_by_user_id",
                    sa.Integer(),
                    sa.ForeignKey("users.id"),
                    nullable=True,
                ),
                sa.Column("last_used_at", sa.DateTime(), nullable=True),
                sa.Column("revoked_at", sa.DateTime(), nullable=True),
                sa.Column(
                    "revoked_by_user_id",
                    sa.Integer(),
                    sa.ForeignKey("users.id"),
                    nullable=True,
                ),
            ],
            [],
            [
                ("ix_api_keys_id", ["id"], False),
                ("ix_api_keys_public_key", ["public_key"], True),
                ("ix_api_keys_tenant_environment", ["tenant_id", "environment_id"], False),
                ("ix_api_keys_tenant_created_at", ["tenant_id", "created_at"], False),
                ("ix_api_keys_tenant_id", ["tenant_id"], False),
            ],
        )

        _sqlite_rebuild_table(
            conn,
            "memberships",
            [
                sa.Column("id", sa.Integer(), primary_key=True),
                sa.Column(
                    "tenant_id",
                    sa.Integer(),
                    sa.ForeignKey("tenants.id"),
                    nullable=False,
                ),
                sa.Column(
                    "user_id",
                    sa.Integer(),
                    sa.ForeignKey("users.id"),
                    nullable=False,
                ),
                sa.Column("role", sa.String(), nullable=False),
                sa.Column("status", sa.String(), nullable=False),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=False),
                sa.Column(
                    "created_by_user_id",
                    sa.Integer(),
                    sa.ForeignKey("users.id"),
                    nullable=True,
                ),
            ],
            [
                sa.UniqueConstraint("tenant_id", "user_id", name="uq_membership_user_tenant"),
            ],
            [
                ("ix_memberships_id", ["id"], False),
                ("ix_memberships_tenant_role", ["tenant_id", "role"], False),
                ("ix_memberships_user_id", ["user_id"], False),
                ("ix_memberships_tenant_id", ["tenant_id"], False),
            ],
        )

        _sqlite_rebuild_table(
            conn,
            "invites",
            [
                sa.Column("id", sa.Integer(), primary_key=True),
                sa.Column(
                    "tenant_id",
                    sa.Integer(),
                    sa.ForeignKey("tenants.id"),
                    nullable=False,
                ),
                sa.Column("email", sa.String(), nullable=False),
                sa.Column("role", sa.String(), nullable=False),
                sa.Column("token_hash", sa.String(), nullable=False),
                sa.Column("expires_at", sa.DateTime(), nullable=False),
                sa.Column("accepted_at", sa.DateTime(), nullable=True),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=False),
                sa.Column(
                    "created_by_user_id",
                    sa.Integer(),
                    sa.ForeignKey("users.id"),
                    nullable=False,
                ),
            ],
            [],
            [
                ("ix_invites_id", ["id"], False),
                ("ix_invites_tenant_id", ["tenant_id"], False),
                ("ix_invites_token_hash", ["token_hash"], True),
                ("ix_invites_tenant_email", ["tenant_id", "email"], False),
                ("ix_invites_tenant_expires_at", ["tenant_id", "expires_at"], False),
            ],
        )

        _sqlite_rebuild_table(
            conn,
            "domain_verifications",
            [
                sa.Column("id", sa.Integer(), primary_key=True),
                sa.Column(
                    "tenant_id",
                    sa.Integer(),
                    sa.ForeignKey("tenants.id"),
                    nullable=False,
                ),
                sa.Column(
                    "website_id",
                    sa.Integer(),
                    sa.ForeignKey("websites.id"),
                    nullable=False,
                ),
                sa.Column("method", sa.String(), nullable=False),
                sa.Column("token", sa.String(), nullable=False),
                sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'pending'")),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=False),
                sa.Column(
                    "created_by_user_id",
                    sa.Integer(),
                    sa.ForeignKey("users.id"),
                    nullable=True,
                ),
                sa.Column("verified_at", sa.DateTime(), nullable=True),
                sa.Column("last_checked_at", sa.DateTime(), nullable=True),
            ],
            [],
            [
                ("ix_domain_verifications_id", ["id"], False),
                ("ix_domain_verifications_tenant_id", ["tenant_id"], False),
                ("ix_domain_verifications_website_id", ["website_id"], False),
                ("ix_domain_verifications_method", ["method"], False),
                ("ix_domain_verifications_token", ["token"], True),
                ("ix_domain_verifications_tenant_website", ["tenant_id", "website_id"], False),
            ],
        )

        _sqlite_rebuild_table(
            conn,
            "feature_entitlements",
            [
                sa.Column("id", sa.Integer(), primary_key=True),
                sa.Column(
                    "tenant_id",
                    sa.Integer(),
                    sa.ForeignKey("tenants.id"),
                    nullable=False,
                ),
                sa.Column("feature", sa.String(), nullable=False),
                sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
                sa.Column("source", sa.String(), nullable=False),
                sa.Column(
                    "source_plan_id",
                    sa.Integer(),
                    sa.ForeignKey("plans.id"),
                    nullable=True,
                ),
                sa.Column(
                    "updated_by_user_id",
                    sa.Integer(),
                    sa.ForeignKey("users.id"),
                    nullable=True,
                ),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=False),
            ],
            [
                sa.UniqueConstraint("tenant_id", "feature", name="uq_feature_entitlement"),
            ],
            [
                ("ix_feature_entitlements_id", ["id"], False),
                ("ix_feature_entitlements_tenant_id", ["tenant_id"], False),
                ("ix_feature_entitlements_feature", ["feature"], False),
            ],
        )

        _sqlite_rebuild_table(
            conn,
            "website_tags",
            [
                sa.Column(
                    "website_id",
                    sa.Integer(),
                    sa.ForeignKey("websites.id"),
                    primary_key=True,
                ),
                sa.Column(
                    "tag_id",
                    sa.Integer(),
                    sa.ForeignKey("project_tags.id"),
                    primary_key=True,
                ),
            ],
            [],
            [
                ("ix_website_tags_website_id", ["website_id"], False),
                ("ix_website_tags_tag_id", ["tag_id"], False),
            ],
        )

        conn.execute(sa.text("PRAGMA foreign_keys=ON"))
        return

    _replace_fk(
        conn,
        "tenants",
        "created_by_user_id",
        "users",
        "NO ACTION",
        "fk_tenants_created_by_user_id",
    )
    _replace_fk(
        conn,
        "websites",
        "created_by_user_id",
        "users",
        "NO ACTION",
        "fk_websites_created_by_user_id",
    )
    _replace_fk(
        conn,
        "api_keys",
        "created_by_user_id",
        "users",
        "NO ACTION",
        "fk_api_keys_created_by_user_id",
    )
    _replace_fk(
        conn,
        "api_keys",
        "revoked_by_user_id",
        "users",
        "NO ACTION",
        "fk_api_keys_revoked_by_user_id",
    )
    _replace_fk(
        conn,
        "memberships",
        "created_by_user_id",
        "users",
        "NO ACTION",
        "fk_memberships_created_by_user_id",
    )
    _replace_fk(
        conn,
        "invites",
        "created_by_user_id",
        "users",
        "NO ACTION",
        "fk_invites_created_by_user_id",
    )
    _replace_fk(
        conn,
        "domain_verifications",
        "created_by_user_id",
        "users",
        "NO ACTION",
        "fk_domain_verifications_created_by_user_id",
    )
    _replace_fk(
        conn,
        "feature_entitlements",
        "updated_by_user_id",
        "users",
        "NO ACTION",
        "fk_feature_entitlements_updated_by_user_id",
    )
    _replace_fk(
        conn,
        "website_tags",
        "website_id",
        "websites",
        "NO ACTION",
        "fk_website_tags_website_id",
    )
    _replace_fk(
        conn,
        "website_tags",
        "tag_id",
        "project_tags",
        "NO ACTION",
        "fk_website_tags_tag_id",
    )

    op.alter_column("invites", "created_by_user_id", existing_type=sa.Integer(), nullable=False)
