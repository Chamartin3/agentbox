"""db source of truth: agent_versions columns + active_agent_versions + agent_meta

Revision ID: c1a8d9f2e4b7
Revises: bb9ee25c0427
Create Date: 2026-05-22 12:00:00.000000

Adds the columns and tables described in PLAN_db_source_of_truth.md /
CLAUDE.md.  Code paths (``get_active_version``, ``startup_sweep`` heal,
``activate_version``) already depend on these — they were silently
removed from the schema in a recent edit pass.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c1a8d9f2e4b7'
down_revision: Union[str, Sequence[str], None] = 'bb9ee25c0427'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'agent_versions',
        sa.Column('config_json', sa.String(), nullable=True),
    )
    op.add_column(
        'agent_versions',
        sa.Column('prompt_content', sa.String(), nullable=True),
    )
    op.add_column(
        'agent_versions',
        sa.Column(
            'source', sa.String(), server_default='manifest', nullable=False
        ),
    )
    op.add_column(
        'agent_versions',
        sa.Column(
            'is_draft', sa.Integer(), server_default='0', nullable=False
        ),
    )

    op.create_table(
        'active_agent_versions',
        sa.Column('agent_id', sa.String(), primary_key=True),
        sa.Column('version_id', sa.Integer(), nullable=False),
        sa.Column('activated_at', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['version_id'], ['agent_versions.id']),
    )

    op.create_table(
        'agent_meta',
        sa.Column('agent_id', sa.String(), primary_key=True),
        sa.Column(
            'sync_mode', sa.String(), server_default='watch', nullable=False
        ),
        sa.Column(
            'export_to_disk',
            sa.Integer(),
            server_default='1',
            nullable=False,
        ),
        sa.Column('source_path', sa.String(), nullable=True),
        sa.Column('source_format', sa.String(), nullable=True),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.Column('updated_at', sa.String(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('agent_meta')
    op.drop_table('active_agent_versions')
    op.drop_column('agent_versions', 'is_draft')
    op.drop_column('agent_versions', 'source')
    op.drop_column('agent_versions', 'prompt_content')
    op.drop_column('agent_versions', 'config_json')
