"""create job queue tables

Revision ID: c0a1b2c3d4e6
Revises: c0a1b2c3d4e5
Create Date: 2026-02-05 13:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c0a1b2c3d4e6"
down_revision = "c0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "job_queue",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("queue_name", sa.String(), nullable=False),
        sa.Column("job_type", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("run_at", sa.DateTime(), nullable=False),
        sa.Column("locked_at", sa.DateTime(), nullable=True),
        sa.Column("locked_by", sa.String(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_job_queue_id", "job_queue", ["id"], unique=False)
    op.create_index("ix_job_queue_queue_name", "job_queue", ["queue_name"], unique=False)
    op.create_index("ix_job_queue_job_type", "job_queue", ["job_type"], unique=False)
    op.create_index("ix_job_queue_tenant_id", "job_queue", ["tenant_id"], unique=False)
    op.create_index(
        "ix_job_queue_queue_status_run_at",
        "job_queue",
        ["queue_name", "status", "run_at"],
        unique=False,
    )
    op.create_index(
        "ix_job_queue_queue_priority_created",
        "job_queue",
        ["queue_name", "priority", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_job_queue_tenant_queue_status",
        "job_queue",
        ["tenant_id", "queue_name", "status"],
        unique=False,
    )

    op.create_table(
        "job_dead_letters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("original_job_id", sa.Integer(), nullable=True),
        sa.Column("queue_name", sa.String(), nullable=False),
        sa.Column("job_type", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("failed_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_job_dead_letters_id", "job_dead_letters", ["id"], unique=False)
    op.create_index("ix_job_dead_letters_queue_name", "job_dead_letters", ["queue_name"], unique=False)
    op.create_index("ix_job_dead_letters_job_type", "job_dead_letters", ["job_type"], unique=False)
    op.create_index("ix_job_dead_letters_tenant_id", "job_dead_letters", ["tenant_id"], unique=False)
    op.create_index(
        "ix_job_dead_letters_queue_failed_at",
        "job_dead_letters",
        ["queue_name", "failed_at"],
        unique=False,
    )
    op.create_index(
        "ix_job_dead_letters_tenant",
        "job_dead_letters",
        ["tenant_id"],
        unique=False,
    )

    op.alter_column("job_queue", "priority", server_default=None)
    op.alter_column("job_queue", "status", server_default=None)
    op.alter_column("job_queue", "attempt_count", server_default=None)
    op.alter_column("job_dead_letters", "attempt_count", server_default=None)


def downgrade():
    op.drop_index("ix_job_dead_letters_tenant", table_name="job_dead_letters")
    op.drop_index("ix_job_dead_letters_queue_failed_at", table_name="job_dead_letters")
    op.drop_index("ix_job_dead_letters_tenant_id", table_name="job_dead_letters")
    op.drop_index("ix_job_dead_letters_job_type", table_name="job_dead_letters")
    op.drop_index("ix_job_dead_letters_queue_name", table_name="job_dead_letters")
    op.drop_index("ix_job_dead_letters_id", table_name="job_dead_letters")
    op.drop_table("job_dead_letters")

    op.drop_index("ix_job_queue_tenant_queue_status", table_name="job_queue")
    op.drop_index("ix_job_queue_queue_priority_created", table_name="job_queue")
    op.drop_index("ix_job_queue_queue_status_run_at", table_name="job_queue")
    op.drop_index("ix_job_queue_tenant_id", table_name="job_queue")
    op.drop_index("ix_job_queue_job_type", table_name="job_queue")
    op.drop_index("ix_job_queue_queue_name", table_name="job_queue")
    op.drop_index("ix_job_queue_id", table_name="job_queue")
    op.drop_table("job_queue")
