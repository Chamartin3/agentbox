"""run_comments table: per-run feedback thread

Revision ID: d4e7b9a3c821
Revises: c1a8d9f2e4b7
Create Date: 2026-05-22 13:00:00.000000

Comments live alongside runs the same way `agent_version_comments`
lives alongside agent versions. The Run Detail page needs a discussion
thread for observed behaviour, post-mortems and review notes — and
without a dedicated table that history had nowhere to live.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e7b9a3c821'
down_revision: Union[str, Sequence[str], None] = 'c1a8d9f2e4b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'run_comments',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('run_id', sa.String(), nullable=False),
        sa.Column('author', sa.String(), nullable=False),
        sa.Column('body', sa.String(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['runs.id']),
    )
    op.create_index(
        'idx_run_comments_run', 'run_comments', ['run_id']
    )


def downgrade() -> None:
    op.drop_index('idx_run_comments_run', table_name='run_comments')
    op.drop_table('run_comments')
