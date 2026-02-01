"""create email queue and add email opt-out

Revision ID: fffff6a7b8c9
Revises: ffffe4f5g6h7
Create Date: 2026-01-30 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "fffff6a7b8c9"
down_revision = "ffffe4f5g6h7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user_profiles",
        sa.Column("email_opt_out", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("user_profiles", "email_opt_out", server_default=None)

    op.create_table(
        "email_queue",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("to_email", sa.String(), nullable=False),
        sa.Column("template_key", sa.String(), nullable=False),
        sa.Column("dedupe_key", sa.String(), nullable=False),
        sa.Column("trigger_event", sa.String(), nullable=True),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "tenant_id",
            "user_id",
            "dedupe_key",
            name="uq_email_queue_dedupe",
        ),
    )
    op.create_index(
        "ix_email_queue_tenant_status_created",
        "email_queue",
        ["tenant_id", "status", "created_at"],
    )


def downgrade():
    op.drop_index("ix_email_queue_tenant_status_created", table_name="email_queue")
    op.drop_table("email_queue")
    op.drop_column("user_profiles", "email_opt_out")
