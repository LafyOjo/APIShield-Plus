"""create access logs table

Revision ID: eeeee
Revises: ddddd
Create Date: 2025-07-05 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'eeeee'
down_revision: Union[str, None] = 'ddddd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'access_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('username', sa.String(), nullable=True),
        sa.Column('path', sa.String(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
    )
    op.create_index(op.f('ix_access_logs_id'), 'access_logs', ['id'], unique=False)
    op.create_index(op.f('ix_access_logs_username'), 'access_logs', ['username'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_access_logs_username'), table_name='access_logs')
    op.drop_index(op.f('ix_access_logs_id'), table_name='access_logs')
    op.drop_table('access_logs')
