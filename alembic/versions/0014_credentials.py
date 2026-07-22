"""Managed credentials + per-workspace credential enablement.

Revision ID: 0014_credentials
Revises: 0013_run_rating
Create Date: 2026-07-30 00:00:00.000000

Two additive tables for the unified credential system:

  - ``managed_credentials`` — credentials added through the web UI, stored
    Fernet-encrypted (``secret_encrypted``); only presence metadata is ever
    read back.
  - ``workspace_credentials`` — which credential ids each workspace has
    enabled. A row's existence means "enabled"; materialized into a run's
    env when the workspace opts into per-workspace credentials.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0014_credentials"
down_revision: str | Sequence[str] | None = "0013_run_rating"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "managed_credentials",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("env_var", sa.String(), nullable=True),
        sa.Column("secret_encrypted", sa.String(), nullable=False),
        sa.Column("last_four", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        if_not_exists=True,
    )
    op.create_table(
        "workspace_credentials",
        sa.Column("workspace_id", sa.String(), primary_key=True),
        sa.Column("credential_id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table("workspace_credentials")
    op.drop_table("managed_credentials")
