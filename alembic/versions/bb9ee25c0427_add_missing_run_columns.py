"""add missing run columns

Revision ID: bb9ee25c0427
Revises: 8aa39c682b93
Create Date: 2026-05-21 20:18:44.309743

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bb9ee25c0427'
down_revision: Union[str, Sequence[str], None] = '8aa39c682b93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add missing columns to runs table."""
    op.add_column('runs', sa.Column('schema_validated_via', sa.String(), nullable=True))
    op.add_column('runs', sa.Column('post_status', sa.String(), nullable=True))
    op.add_column('runs', sa.Column('post_errors', sa.String(), nullable=True))


def downgrade() -> None:
    """Drop added columns."""
    op.drop_column('runs', 'post_errors')
    op.drop_column('runs', 'post_status')
    op.drop_column('runs', 'schema_validated_via')
